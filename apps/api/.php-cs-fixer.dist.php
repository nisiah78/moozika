<?php

/*
 * Style — Niveau 2 de la porte pré-commit (`make lint-php`).
 * Aligné sur .editorconfig : 4 espaces, LF, newline finale, pas d'espaces en fin de ligne.
 */

$finder = (new PhpCsFixer\Finder())
    ->in(__DIR__.'/src')
    ->in(__DIR__.'/config')
    ->append([__FILE__]);

return (new PhpCsFixer\Config())
    ->setRules([
        '@Symfony' => true,
        '@PSR12' => true,
        'declare_strict_types' => false,
    ])
    ->setFinder($finder)
    ->setCacheFile(__DIR__.'/var/.php-cs-fixer.cache');
