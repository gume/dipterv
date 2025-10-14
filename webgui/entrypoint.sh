#!/bin/bash
set -e

echo "Running pre-start setup..."

chown -R www-data:www-data /data
chown -R www-data:www-data /db

# create a symlink from /data to /var/www/html/descriptions if it doesn't exist
if [ ! -L /var/www/html/descriptions ]; then
    echo "Creating symlink from /data to /var/www/html/descriptions"
    ln -s /data /var/www/html/descriptions
fi

echo "Entrypoint args: $@"

# Call the original entrypoint with its arguments
exec /usr/local/bin/docker-php-entrypoint "$@"
