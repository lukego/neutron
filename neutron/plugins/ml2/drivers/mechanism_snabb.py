# Copyright (c) 2014 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
# @author: Rahul Mohan Rekha
# @author: Luke Gorrie
# @author: Nikolay Nikolaev

import netaddr

from neutron.common import constants as n_const
from neutron.extensions import portbindings
from neutron.openstack.common import log
from neutron.plugins.ml2 import driver_api as api

from oslo.config import cfg

LOG = log.getLogger(__name__)

snabb_opts = [
    cfg.ListOpt('piesss_ports',
                default=[],
                help=_("List of <host>|<port>|<gbps>|<vlan0>|<address0> "
                       "tuples defining all physical ports used for PIESSS."))
]

cfg.CONF.register_opts(snabb_opts, "ml2_snabb")


class SnabbMechanismDriver(api.MechanismDriver):

    """Mechanism Driver for Snabb NFV.

    This driver implements bind_port to assign provider VLAN networks
    to Snabb NFV. Snabb NFV is a separate networking
    implementation that forwards packets to virtual machines using its
    own vswitch (Snabb Switch) on compute nodes.
    """

    def initialize(self):
        self.vif_type = portbindings.VIF_TYPE_VHOSTUSER
        self._parse_piesss_ports()
        self.allocated_bandwidth = None

    def _parse_piesss_ports(self):
        conf = cfg.CONF.ml2_snabb.piesss_ports
        self.hosts = {}
        for entry in conf:
            LOG.debug("entry: %s", entry)
            host, port, gbps, vlan0, address0 = entry.split('|')
            gbps = int(gbps)
            vlan0 = int(vlan0)
            address0 = netaddr.IPAddress(address0)
            self.hosts.setdefault(host, {})[port] = {'name': port,
                                                     'allocated': 0,
                                                     'gbps': gbps,
                                                     'vlan0': vlan0,
                                                     'address0': address0}
            LOG.debug("hosts[%s][%s] = %s", host, port, self.hosts[host][port])

    def _choose_port(self, hosts_and_ports, host_id, gbps):
        # Port that best fits, and how many gbps it has available.
        best_fit, best_fit_avail = None, None
        for portname, port in hosts_and_ports[host_id].items():
            avail = port['gbps'] - port['allocated']
            if (best_fit == None or avail < best_fit_avail) and avail >= gbps:
                # Found a better (tighter) fit
                best_fit, best_fit_avail = port, avail
        if best_fit is not None:
            LOG.error("No port found on host %(host_id) with %(gbps) "
                      "Gbps available",
                      {'host_id': host_id,
                       'gbps': gbps})
            assert not best_fit is None
        LOG.info("Selected port %s with %s Gbps available",
                 portname, best_fit_avail)
        return best_fit

    def bind_port(self, context):
        LOG.debug("Attempting to bind port %(port)s on network %(network)s",
                  {'port': context.current['id'],
                   'network': context.network.current['id']})
        if not self.allocated_bandwidth:
            self._scan_bandwidth_allocations()
        for segment in context.network.network_segments:
            if self.check_segment(segment):
                gbps = 8
                host_id = context.current['binding:host_id']
                port = self._choose_port(context, host_id, gbps)
                allocated_ip = netaddr.IPAddress('2003::10')
                # piesss_ip = netaddr.IPAddress('2004::1:0:0:0:0')
                piesss_ip = port['address0']
                addr_mask = netaddr.IPAddress('::ffff:ffff:ffff:ffff')
                vm_ip = (allocated_ip & addr_mask) | piesss_ip
                vif_details = {portbindings.CAP_PORT_FILTER: True,
                               'piesss_host': host_id,
                               'piesss_ip': vm_ip,
                               'piesss_vlan': port['vlan0'],
                               'piesss_port': port['name']}
                port.allocated += gbps
                # TODO(lukego) Support binding on a specific host based on
                # networking requirements.
                context.set_binding(segment[api.ID],
                                    self.vif_type,
                                    vif_details,
                                    status=n_const.PORT_STATUS_ACTIVE)
                LOG.debug("Bound using segment: %s", segment)
                return
            else:
                LOG.debug("Refusing to bind port for segment ID %(id)s, "
                          "segment %(seg)s, phys net %(physnet)s, and "
                          "network type %(nettype)s",
                          {'id': segment[api.ID],
                           'seg': segment[api.SEGMENTATION_ID],
                           'physnet': segment[api.PHYSICAL_NETWORK],
                           'nettype': segment[api.NETWORK_TYPE]})

    def _scan_bandwidth_allocations(self, context):
        self.allocated_bandwidth = {}
        dbcontext = context._plugin_context
        ports = context._plugin.get_ports(dbcontext)
        for port in ports:
            self._scan_port_bandwidth_allocation(port)

    def _scan_port_bandwidth_allocation(self, port):
        profile = jsonutils.loads(port[portbindings.PROFILE])
        details = jsonutils.loads(port[portbindings.VIF_DETAILS])
        host = details.get('piesss_host')
        port = details.get('piesss_port')
        gbps = profile.get('piesss_gbps')
        if host and port and gbps:
            LOG.debug("Port %(port_id)s: %(gbps)s Gbps bandwidth reserved on "
                      "host %(host)s port %(port)s",
                      {'port_id': port['id'],
                       'gbps': gbps,
                       'host': host,
                       'port': port})
            self.allocated_bandwidth.setdefault((host,port), 0)
            self.allocated_bandwidth[(host,port)] += float(gbps)
        else
        LOG.debug("Port %s: no bandwidth reservation", port['id'])

    def check_segment(self, segment):
        """Verify a segment is valid for the SnabbSwitch MechanismDriver.

        Verify the requested segment is supported by Snabb and return True or
        False to indicate this to callers.
        """
        return segment[api.NETWORK_TYPE] == 'piesss'
