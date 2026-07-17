#!/usr/bin/env sh
CONTROL="python3 -u manage.py"
migrate_func() { ${CONTROL} migrate; }
ui () {
    migrate_func
    python3 superuser.py
    ${CONTROL} sopds_server start --host 0.0.0.0 --port 8000 "$@"
}
daemon () {
    migrate_func
    python3 superuser.py
    ${CONTROL} sopds_scanner start "$@"
}
case $1 in
    migrate) shift; ${CONTROL} migrate "$@";;
    createsuperuser) shift; ${CONTROL} createsuperuser --noinput "$@";;
    ui) shift; ui "$@";;
    daemon) shift; daemon "$@";;
    help) echo "Usage: migrate | createsuperuser | ui | daemon";;
    *) echo "Cannot find command" && exit 1;;
esac
