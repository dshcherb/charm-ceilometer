import os

from collections import OrderedDict

from charmhelpers.contrib.openstack import (
    templating,
    context,
)
from ceilometer_contexts import (
    ApacheSSLContext,
    LoggingConfigContext,
    MongoDBContext,
    CeilometerContext,
    HAProxyContext
)
from charmhelpers.contrib.openstack.utils import (
    get_os_codename_package,
    get_os_codename_install_source,
    configure_installation_source
)
from charmhelpers.core.hookenv import config, log
from charmhelpers.fetch import apt_update, apt_install, apt_upgrade
from copy import deepcopy

HAPROXY_CONF = '/etc/haproxy/haproxy.cfg'
CEILOMETER_CONF_DIR = "/etc/ceilometer"
CEILOMETER_CONF = "%s/ceilometer.conf" % CEILOMETER_CONF_DIR
HTTPS_APACHE_CONF = "/etc/apache2/sites-available/openstack_https_frontend"
HTTPS_APACHE_24_CONF = "/etc/apache2/sites-available/" \
    "openstack_https_frontend.conf"
CLUSTER_RES = 'grp_ceilometer_vips'

CEILOMETER_SERVICES = [
    'ceilometer-agent-central',
    'ceilometer-collector',
    'ceilometer-api'
]

CEILOMETER_DB = "ceilometer"
CEILOMETER_SERVICE = "ceilometer"

CEILOMETER_PACKAGES = [
    'haproxy',
    'apache2',
    'ceilometer-agent-central',
    'ceilometer-collector',
    'ceilometer-api'
]

ICEHOUSE_PACKAGES = [
    'ceilometer-alarm-notifier',
    'ceilometer-alarm-evaluator',
    'ceilometer-agent-notification'
]

CEILOMETER_ROLE = "ResellerAdmin"


CONFIG_FILES = OrderedDict([
    (CEILOMETER_CONF, {
        'hook_contexts': [context.IdentityServiceContext(),
                          context.AMQPContext(ssl_dir=CEILOMETER_CONF_DIR),
                          LoggingConfigContext(),
                          MongoDBContext(),
                          CeilometerContext(),
                          context.SyslogContext()],
        'services': CEILOMETER_SERVICES
    }),
    (HAPROXY_CONF, {
        'hook_contexts': [context.HAProxyContext(),
                          HAProxyContext()],
        'services': ['haproxy'],
    }),
    (HTTPS_APACHE_CONF, {
        'hook_contexts': [ApacheSSLContext()],
        'services': ['apache2'],
    }),
    (HTTPS_APACHE_24_CONF, {
        'hook_contexts': [ApacheSSLContext()],
        'services': ['apache2'],
    })
])

TEMPLATES = 'templates'


def register_configs():
    """
    Register config files with their respective contexts.
    Regstration of some configs may not be required depending on
    existing of certain relations.
    """
    # if called without anything installed (eg during install hook)
    # just default to earliest supported release. configs dont get touched
    # till post-install, anyway.
    release = get_os_codename_package('ceilometer-common', fatal=False) \
        or 'grizzly'
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)

    for conf in CONFIG_FILES:
        configs.register(conf, CONFIG_FILES[conf]['hook_contexts'])

    if os.path.exists('/etc/apache2/conf-available'):
        configs.register(HTTPS_APACHE_24_CONF,
                         CONFIG_FILES[HTTPS_APACHE_24_CONF]['hook_contexts'])
    else:
        configs.register(HTTPS_APACHE_CONF,
                         CONFIG_FILES[HTTPS_APACHE_CONF]['hook_contexts'])
    return configs


def restart_map():
    '''
    Determine the correct resource map to be passed to
    charmhelpers.core.restart_on_change() based on the services configured.

    :returns: dict: A dictionary mapping config file to lists of services
                    that should be restarted when file changes.
    '''
    _map = {}
    for f, ctxt in CONFIG_FILES.iteritems():
        svcs = []
        for svc in ctxt['services']:
            svcs.append(svc)
        if svcs:
            _map[f] = svcs
    return _map


def get_ceilometer_context():
    ''' Retrieve a map of all current relation data for agent configuration '''
    ctxt = {}
    for hcontext in CONFIG_FILES[CEILOMETER_CONF]['hook_contexts']:
        ctxt.update(hcontext())
    return ctxt


def do_openstack_upgrade(configs):
    """
    Perform an upgrade.  Takes care of upgrading packages, rewriting
    configs, database migrations and potentially any other post-upgrade
    actions.

    :param configs: The charms main OSConfigRenderer object.
    """
    new_src = config('openstack-origin')
    new_os_rel = get_os_codename_install_source(new_src)

    log('Performing OpenStack upgrade to %s.' % (new_os_rel))

    configure_installation_source(new_src)
    dpkg_opts = [
        '--option', 'Dpkg::Options::=--force-confnew',
        '--option', 'Dpkg::Options::=--force-confdef',
    ]
    apt_update(fatal=True)
    apt_upgrade(options=dpkg_opts, fatal=True, dist=True)
    apt_install(packages=get_packages(),
                options=dpkg_opts,
                fatal=True)

    # set CONFIGS to load templates from new release
    configs.set_release(openstack_release=new_os_rel)


def get_packages():
    packages = deepcopy(CEILOMETER_PACKAGES)
    if (get_os_codename_install_source(config('openstack-origin'))
            >= 'icehouse'):
        packages = packages + ICEHOUSE_PACKAGES
    return packages
