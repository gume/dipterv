FROM php:8.2-apache

# Hide version info; the code in html/ is mounted at /var/www/html by docker-compose.yml.
RUN { echo "ServerTokens Prod"; echo "ServerSignature Off"; } > /etc/apache2/conf-available/hardening.conf \
    && a2enconf hardening \
    && { echo "expose_php=0"; } > /usr/local/etc/php/conf.d/hardening.ini \
    && { echo "SetEnvIf Authorization \"(.*)\" HTTP_AUTHORIZATION=\$1"; } > /etc/apache2/conf-available/auth.conf \
    && a2enconf auth
