#!/bin/sh

case "$-" in
*i*)
    if [ -x /usr/bin/apk ]; then
        printf ' Package manager  apk update | apk add <package>\n\n'
    fi
    ;;
esac
