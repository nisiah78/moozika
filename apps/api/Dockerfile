FROM php:8.3-cli-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        git unzip libpq-dev libzip-dev \
    && docker-php-ext-install pdo_pgsql zip pcntl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# Aucun php.ini n'est charge par defaut dans l'image php:*-cli.
COPY docker/php.ini /usr/local/etc/php/conf.d/moozika.ini

WORKDIR /var/www/api

COPY . .
RUN mkdir -p var \
    && composer install --no-interaction --prefer-dist --no-security-blocking \
    || composer install --no-interaction --prefer-dist

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
CMD ["php", "-S", "0.0.0.0:8080", "-t", "public"]
