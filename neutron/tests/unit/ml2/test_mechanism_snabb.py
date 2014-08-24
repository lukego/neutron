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
# @author: Nikolay Nikolaev
# @author: Luke Gorrie

import netaddr

from neutron.plugins.common import constants
from neutron.plugins.ml2 import config as config
from neutron.plugins.ml2 import driver_api as api
from neutron.plugins.ml2.drivers import mechanism_snabb
from neutron.tests.unit import test_db_plugin as test_plugin

PLUGIN_NAME = 'neutron.plugins.ml2.plugin.Ml2Plugin'


class SnabbTestCase(test_plugin.NeutronDbPluginV2TestCase):

    def setUp(self):
        # Enable the test mechanism driver to ensure that
        # we can successfully call through to all mechanism
        # driver apis.
        config.cfg.CONF.set_override('mechanism_drivers',
                                     ['logger', 'snabb'],
                                     'ml2')
        super(SnabbTestCase, self).setUp(PLUGIN_NAME)
        self.port_create_status = 'DOWN'
        self.segment = {'api.NETWORK_TYPE': ""}
        self.mech = mechanism_snabb.SnabbMechanismDriver()

    def test_check_segment(self):
        """Validate the check_segment call."""
        self.segment[api.NETWORK_TYPE] = constants.TYPE_LOCAL
        self.assertFalse(self.mech.check_segment(self.segment))
        self.segment[api.NETWORK_TYPE] = constants.TYPE_FLAT
        self.assertFalse(self.mech.check_segment(self.segment))
        self.segment[api.NETWORK_TYPE] = constants.TYPE_VLAN
        self.assertFalse(self.mech.check_segment(self.segment))
        self.segment[api.NETWORK_TYPE] = constants.TYPE_GRE
        self.assertFalse(self.mech.check_segment(self.segment))
        self.segment[api.NETWORK_TYPE] = constants.TYPE_VXLAN
        self.assertFalse(self.mech.check_segment(self.segment))
        self.segment[api.NETWORK_TYPE] = 'piesss'
        self.assertTrue(self.mech.check_segment(self.segment))
        # Validate a network type not currently supported
        self.segment[api.NETWORK_TYPE] = 'mpls'
        self.assertFalse(self.mech.check_segment(self.segment))


class SnabbMechanismTestPiesss(SnabbTestCase):

    def test_choose_available_port(self):
        hosts_and_ports = {'host1':
                           {'port0':
                            {'name': 'port0',
                             'allocated': 10, 'gbps': 10, 'vlan0': 100,
                             'address0': netaddr.IPAddress('2003:1::0')},
                            'port1':
                            {'name': 'port1',
                             'allocated': 5, 'gbps': 10, 'vlan0': 100,
                             'address0': netaddr.IPAddress('2003:2::0')},
                            'port2':
                            {'name': 'port2',
                             'allocated': 0, 'gbps': 10, 'vlan0': 200,
                             'address0': netaddr.IPAddress('2003:3::0')}}}
        port = self.mech._choose_port(hosts_and_ports, 'host1', 4)
        self.assertEqual(port['name'], 'port1')
        port = self.mech._choose_port(hosts_and_ports, 'host1', 5)
        self.assertEqual(port['name'], 'port1')
        port = self.mech._choose_port(hosts_and_ports, 'host1', 6)
        self.assertEqual(port['name'], 'port2')

    def test_choose_overloaded_port(self):
        hosts_and_ports = {'host1':
                           {'port0':
                            {'name': 'port0',
                             'allocated': 15, 'gbps': 10, 'vlan0': 100,
                             'address0': netaddr.IPAddress('2003:1::0')},
                            'port1':
                            {'name': 'port1',
                             'allocated': 11, 'gbps': 10, 'vlan0': 100,
                             'address0': netaddr.IPAddress('2003:2::0')},
                            'port2':
                            {'name': 'port2',
                             'allocated': 20, 'gbps': 10, 'vlan0': 200,
                             'address0': netaddr.IPAddress('2003:3::0')}}}
        port = self.mech._choose_port(hosts_and_ports, 'host1', 1)
        self.assertEqual(port['name'], 'port1')
        port = self.mech._choose_port(hosts_and_ports, 'host1', 5)
        self.assertEqual(port['name'], 'port1')
        port = self.mech._choose_port(hosts_and_ports, 'host1', 20)
        self.assertEqual(port['name'], 'port1')


class SnabbMechanismTestBasicGet(test_plugin.TestBasicGet, SnabbTestCase):
    pass


class SnabbMechanismTestNetworksV2(test_plugin.TestNetworksV2, SnabbTestCase):
    pass


class SnabbMechanismTestPortsV2(test_plugin.TestPortsV2, SnabbTestCase):
    pass
