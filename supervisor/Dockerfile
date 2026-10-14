FROM php:8.2-apache

# Hide version info and keep sessions out of the web root.
RUN { echo "ServerTokens Prod"; echo "ServerSignature Off"; } > /etc/apache2/conf-available/hardening.conf \
    && a2enconf hardening \
    && { echo "expose_php=0"; echo "session.cookie_httponly=1"; echo "session.cookie_samesite=Strict"; echo "session.use_strict_mode=1"; } \
       > /usr/local/etc/php/conf.d/hardening.ini

# The code in html/ is mounted read-only at /var/www/html by docker-compose.yml.
