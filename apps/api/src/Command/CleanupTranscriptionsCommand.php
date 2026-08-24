<?php

declare(strict_types=1);

namespace App\Command;

use App\Entity\TranscriptionJob;
use App\Repository\TranscriptionJobRepository;
use App\Service\TranscriptionPublisher;
use App\Service\TranscriptionService;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\Console\Attribute\AsCommand;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Output\OutputInterface;
use Symfony\Component\Console\Style\SymfonyStyle;

/**
 * Entretien des jobs de transcription : reprise des zombies + purge.
 *
 * Deux problèmes distincts, résolus au même endroit parce qu'ils se déclenchent au même
 * rythme (un passage périodique) :
 *
 * 1. **Zombies.** Un worker tué laisse un job en `running` pour toujours : personne ne
 *    viendra le terminer, et la carte tourne indéfiniment côté navigateur. On les repère
 *    sur `updatedAt` — fiable car le handler le remonte à chaque progression persistée.
 *
 * 2. **Rétention.** En asynchrone, chaque upload crée une ligne, alors qu'avant une
 *    mauvaise transcription était jetée sans jamais toucher la base. Il faut donc une
 *    politique explicite, sinon la table croît sans fin.
 */
#[AsCommand(
    name: 'app:transcriptions:cleanup',
    description: 'Reprend les jobs zombies et purge les jobs terminés anciens.',
)]
final class CleanupTranscriptionsCommand extends Command
{
    /**
     * Doit rester COHÉRENT avec `redeliver_timeout` (7200 s) de messenger.yaml : en deçà, on
     * déclarerait mort un job que Messenger va encore redélivrer légitimement.
     */
    private const STALE_AFTER = '-3 hours';

    /** Les échecs restent consultables un moment : c'est leur seul intérêt. */
    private const KEEP_TERMINAL = '-7 days';

    public function __construct(
        private readonly EntityManagerInterface $em,
        private readonly TranscriptionJobRepository $jobs,
        private readonly TranscriptionService $transcriptions,
        private readonly TranscriptionPublisher $publisher,
    ) {
        parent::__construct();
    }

    protected function configure(): void
    {
        $this->addOption('dry-run', null, InputOption::VALUE_NONE, 'N\'écrit rien, affiche ce qui serait fait.');
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $io = new SymfonyStyle($input, $output);
        $dryRun = (bool) $input->getOption('dry-run');

        $reaped = $this->reapStale($io, $dryRun);
        $purged = $this->purgeTerminal($io, $dryRun);

        $io->success(sprintf(
            '%d job(s) zombie(s) repris, %d job(s) purgé(s).%s',
            $reaped,
            $purged,
            $dryRun ? ' (dry-run : rien écrit)' : ''
        ));

        return Command::SUCCESS;
    }

    private function reapStale(SymfonyStyle $io, bool $dryRun): int
    {
        $stale = $this->jobs->findStale(new \DateTimeImmutable(self::STALE_AFTER));
        foreach ($stale as $job) {
            $io->text(sprintf(
                '  zombie : %s (running depuis %s)',
                $job->getId()->toRfc4122(),
                $job->getUpdatedAt()->format(\DateTimeInterface::ATOM)
            ));
            if ($dryRun) {
                continue;
            }

            $job->setStatus(TranscriptionJob::STATUS_FAILED)
                ->setError(
                    'worker_lost',
                    'La transcription a été interrompue (le service de traitement s\'est arrêté). Relancez l\'import.',
                    'job sans progression depuis '.self::STALE_AFTER
                )
                ->setMessage('Transcription interrompue.')
                ->bumpUpdatedAt();
            $this->transcriptions->discardSource($job);
        }

        if (!$dryRun && [] !== $stale) {
            $this->em->flush();
            // Publier APRÈS le flush : le navigateur doit voir l'état réellement enregistré.
            foreach ($stale as $job) {
                $this->publisher->publish($job);
            }
        }

        return \count($stale);
    }

    private function purgeTerminal(SymfonyStyle $io, bool $dryRun): int
    {
        $old = $this->jobs->findTerminalBefore(new \DateTimeImmutable(self::KEEP_TERMINAL));
        foreach ($old as $job) {
            $io->text(sprintf('  purge : %s (%s)', $job->getId()->toRfc4122(), $job->getStatus()));
            if ($dryRun) {
                continue;
            }
            // La source devrait déjà être partie (le handler la jette), mais un job zombie
            // d'avant ce nettoyage peut en avoir laissé une.
            $this->transcriptions->discardSource($job);
            $this->em->remove($job);
        }

        if (!$dryRun && [] !== $old) {
            $this->em->flush();
        }

        return \count($old);
    }
}
