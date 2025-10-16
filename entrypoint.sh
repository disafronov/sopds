#!/usr/bin/env sh

CONTROL="python3 -u manage.py"

config() {
    chmod a+rwX /srv 2> /dev/null || true
    ## config
    test -f /srv/settings.py && ( echo "Existing config detected, saving default config to /srv/settings.py.default"; cp -f /home/sopds/sopds/settings.py /srv/settings.py.default ) || ( echo "Existing config is absent, creating a new one from default at /srv/settings.py"; cp -f /home/sopds/sopds/settings.py /srv/settings.py )
    rm -rf /home/sopds/sopds/settings.py
    ln -sf /srv/settings.py /home/sopds/sopds/settings.py
    # access rights
    chmod -R a+rwX /srv 2> /dev/null || true
    # essential setup
    ${CONTROL} migrate
    python3 superuser.py
    ${CONTROL} sopds_util setconf SOPDS_ROOT_LIB '/books'
    ${CONTROL} sopds_util setconf SOPDS_ZIPSCAN True
    ${CONTROL} sopds_util setconf SOPDS_ZIPCODEPAGE 'utf-8'
    ${CONTROL} sopds_util setconf SOPDS_DELETE_LOGICAL True
    ${CONTROL} sopds_util setconf SOPDS_INPX_ENABLE True
    ${CONTROL} sopds_util setconf SOPDS_INPX_SKIP_UNCHANGED True
    ${CONTROL} sopds_util setconf SOPDS_INPX_TEST_ZIP True
    ${CONTROL} sopds_util setconf SOPDS_INPX_TEST_FILES True
    ${CONTROL} sopds_util setconf SOPDS_SCAN_START_DIRECTLY True
}

ui () {
    config

    # Start UI
    exec ${CONTROL} sopds_server start --host 0.0.0.0 --port 8000 $@
}

daemon () {
    config

    # Start daemon
    exec ${CONTROL} sopds_scanner start $@
}

help () {
    echo "You can run UI with 'ui' parameter"
    echo "You can run update daemon with 'daemon' parameter"
}

case $1 in
    ui) shift && ui $@;;
    daemon) shift && daemon $@;;
    help) shift && help $@;;
    *) echo "Cannot find command" && exit 1;;
esac
