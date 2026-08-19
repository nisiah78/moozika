<?php

declare(strict_types=1);

namespace App\ApiResource;

use ApiPlatform\Metadata\ApiResource;
use ApiPlatform\Metadata\Get;

/**
 * Endpoint de health-check.
 */
#[ApiResource(
    shortName: 'Health',
    routePrefix: '',
    operations: [
        new Get(
            uriTemplate: '/health',
            name: 'health',
            provider: \App\State\HealthProvider::class,
            read: false,
            deserialize: false,
        ),
    ],
)]
final class HealthResource
{
    public string $status = 'ok';
}

