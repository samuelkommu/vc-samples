# Copyright 2016-2020 VMware, Inc.
# SPDX-License-Identifier: BSD-2

# The BSD-2 license (the "License") set forth below applies to this entire script.  
# You may not use this file except in compliance with the License.

# BSD-2 License 
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following 
# conditions are met:
# Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer 
# in the documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, 
# BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT 
# SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL 
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS 
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE 
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Purpose:  vMotion to a specific VIF
#
# Modified version of https://github.com/dixonly/samples/blob/main/vmotion.py to allow using VIF for vMotion during V2T Migration
# Migration Coordinator's Modular Migration feature.
# Note:  Excpects resource pool "nsxt" on destination cluster.  This is hard coded and should be fixed at some point.
#

from pyVim import connect
from pyVmomi import vim
from pyVmomi import vmodl

import atexit
import argparse
import subprocess
import ssl

def parseParameters():

    parser = argparse.ArgumentParser(
            description='Arguments to connect to vCenter to add a hosts to a cluster')
    parser.add_argument('-s', '--sourcevc',
            required = True,
            action = 'store',
            help = 'Source Vcenter server name or IP')
    parser.add_argument('-d', '--destvc',
                        required=False,
                        action='store',
                        help="Destination VC server name or IP")
    
    parser.add_argument('-u', '--user',
            required=True,
            action='store',
            help='User name to connect to vcenter')
    parser.add_argument('-p', '--password',
            required=True,
            action='store',
            help = 'Password for connection to vcenter')
    parser.add_argument('-c', '--cluster',
            required=False,
            action='store',
            help = 'Cluster name to poweron VM. Overides the --servers argument ')
    parser.add_argument("-e", '--server',
            required=False,
            action = 'store',
            help = "ESXi server to power on VM.  Ignored if servers provided")
    parser.add_argument('-v', '--datastore',
                        required=False,
                        help="Destination datastore volume")
    parser.add_argument('-l', '--network',
                        required=False, nargs="*",
                        help="Destination network")
    parser.add_argument("-n", '--name',
            required = False,
            action='store',
            help = "VM name or name pattern to match for poweron ")


    args = parser.parse_args()
    if not args.server and not args.cluster:
        print("Either destination server or cluster must be provided")
        return False
    return args

def getObject(inv, vimtype, name, verbose=False):
    """
    Get object by name from vcenter inventory
    """

    obj = None
    container = inv.viewManager.CreateContainerView(inv.rootFolder, vimtype, True)
    for i in container.view:
        try:
            if verbose:
                print("Checking %s %s against reference %s" %(i.name, i._moId, name))
            if i.name == name:
                obj = i
                break
        except vmodl.fault.ManagedObjectNotFound:
            #print("VM %s no longer exist")
            # This is if object was deleted after container view was created
            pass
    return obj

def setupNetworks(vm, host, networks, vif_id):
    # this requires vsphere 7 API
    nics = []
    for d in vm.config.hardware.device:
        if isinstance(d, vim.vm.device.VirtualEthernetCard):
            nics.append(d)


    if len(nics) > len(networks):
        print("not enough networks for %d nics on vm" %len(nics))
        return None

    netdevs = []
    for i in range(0,len(nics)):
        v = nics[i]
        n = networks[i]
        if isinstance(n, vim.OpaqueNetwork):
            # Is the source opaque net same as destination?
            opaque=False
            if isinstance(v.backing, vim.vm.device.VirtualEthernetCard.OpaqueNetworkBackingInfo):
                if v.backing.opaqueNetworkId == n.summary.opaqueNetworkId:
                    opaque=True
                    originalLs=v.backing.opaqueNetworkId

            v.backing = vim.vm.device.VirtualEthernetCard.OpaqueNetworkBackingInfo()
            v.backing.opaqueNetworkId = n.summary.opaqueNetworkId
            v.backing.opaqueNetworkType = n.summary.opaqueNetworkType
            v.externalId = vif_id
               
        elif isinstance(n, vim.DistributedVirtualPortgroup):
            # create dvpg handling
            vdsPgConn = vim.dvs.PortConnection()
            vdsPgConn.portgroupKey = n.key
            vdsPgConn.switchUuid = n.config.distributedVirtualSwitch.uuid
            v.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
            v.backing.port = vdsPgConn
        else:
            v.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            v.backing.network = n
            v.backing.deviceName = n.name

        virdev = vim.vm.device.VirtualDeviceSpec()
        virdev.device = v
        virdev.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
        netdevs.append(virdev)
    return netdevs
def main():
    print("This script is not supported by VMware.  Use at your own risk")
    args = parseParameters()
    password = args.password
    if hasattr(ssl, 'SSLContext'):
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        context.verify_mode=ssl.CERT_NONE
        si = connect.SmartConnect(host=args.sourcevc, user=args.user, pwd=password, sslContext=context)
    else:
        si = connect.SmartConnect(host=args.sourcevc, user=args.user, pwd=password)

    if not si:
        print("Could not connect to source vcenter: %s " %args.sourcevc)
        return -1
    else:
        print("Connect to vcenter: %s" %args.sourcevc)
        atexit.register(connect.Disconnect, si)

    if not args.destvc or args.sourcevc == args.destvc:
        di = si
    else:
        if hasattr(ssl, 'SSLContext'):
            context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            context.verify_mode=ssl.CERT_NONE
            di = connect.SmartConnect(host=args.destvc, user=args.user, pwd=password, sslContext=context)
        else:
            di = connect.SmartConnect(host=args.destvc, user=args.user, pwd=password)
        if not di:
            print("Could not connect to destination vcenter: %s " %args.destvc)
            return -1
        else:
            print("Connect to vcenter: %s" %args.destvc)
            atexit.register(connect.Disconnect, di)

    
    sinv = si.RetrieveContent()
    sdc = sinv.rootFolder.childEntity[0]

    if args.destvc:
        dinv = di.RetrieveContent()
        ddc = dinv.rootFolder.childEntity[0]
    else:
        dinv = sinv
        ddc = sdc
        
    relocSpec = vim.vm.RelocateSpec()
    #print(sinv)
    #print(dinv)
    if sinv != dinv:
        if not args.server and not args.cluster and not args.datastore and not args.network:
            print("XV Vmotion requires host, cluster, datastore, and network")
            return None

        up = vim.ServiceLocator.NamePassword(username=args.user, password=password)
        sl = vim.ServiceLocator(credential=up,
                                instanceUuid=dinv.about.instanceUuid,
                                url="https://%s" % args.destvc)
        relocSpec.service = sl

    vm = getObject(sinv, [vim.VirtualMachine], args.name, verbose=False)
    rp = getObject(sinv, [vim.ResourcePool], "nsxt")
    print rp
	
    if not vm:
        print("VM %s not found" %args.name)
        return
    else:
        print("VM %s %s found" % (vm.name, vm._moId)) 

    host=None
    if args.server:
        host = getObject(dinv, [vim.HostSystem], args.server)
        if not host:
            print("Host %s not found" %args.server)
            return
        else:
            print("Destination host %s found." % host.name)
                

    cluster=None
    if  args.cluster:
        cluster = getObject(dinv, [vim.ClusterComputeResource], args.cluster)
        if not cluster:
            print("Cluster %s not found" % args.cluster)
            return
        else:
            print("Destination cluster %s found, checking for DRS recommendation..." % cluster.name)
            if host and host.parent.resourcePool != cluster.resourcePool:
                print("Destination host %s and cluster %s are not resource pool"
                      %(host.name, cluster.name))
                return
            if not cluster.configuration.drsConfig.enabled and not host:
                print("Destination cluster %s is not DRS enabled, must specify host"
                      %cluster.name)
                return

            if not host and cluster.resourcePool == vm.resourcePool:
                print("Must provide host when migrating within same cluster")
                return

            if not host:
                rhost = cluster.RecommendHostsForVm(vm=vm, pool=cluster.resourcePool)
                if len(rhost) == 0:
                    print("No hosts found in cluster %s from DRS recommendation for migration"
                          %args.cluster)
                    return
                else:
                    print("DRS recommends %d hosts" %len(rhost))
                    host = rhost[0].host
    if host:
        relocSpec.host = host
        relocSpec.pool = rp        
    if cluster:
        #relocSpec.pool = cluster.resourcePool
        relocSpec.pool = rp
        
    datastore=None
    if args.datastore:
        datastore = getObject(dinv, [vim.Datastore], args.datastore)
        if not datastore:
            print("Datastore %s not found" % args.datastore)
            return
        else:
            print("Destination datastore  %s found." % datastore.name)
            relocSpec.datastore = datastore

    networks=[]
    for n in args.network:
        print("Searching VCenter for destination network(s)")
        network = getObject(dinv, [vim.Network], n, verbose=False)
        if not network:
            print("Network %s not found" % args.network)
            return 
        else:
            print("Destination network %s found." % network.name)
            networks.append(network)

    devices = vm.config.hardware.device
    nic_devices = [device for device in devices if isinstance(device, vim.vm.device.VirtualEthernetCard)]
    vnic_changes = []
    for device in nic_devices:
        vif_id = vm.config.instanceUuid + ":" + str(device.key)
        netSpec=setupNetworks(vm, host, networks, vif_id)
        relocSpec.deviceChange = netSpec
        print("Initiating migration of VM %s" %args.name)
        vm.RelocateVM_Task(spec=relocSpec, priority=vim.VirtualMachine.MovePriority.highPriority)

if __name__ == "__main__":
    main()
