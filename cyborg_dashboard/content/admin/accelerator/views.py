#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from django.utils.translation import gettext_lazy as _

from horizon import exceptions
from horizon import tables

from openstack_dashboard import api

from cyborg_dashboard.api import cyborg as cyborg_api
from cyborg_dashboard.content.admin.accelerator import tables as accelerator_tables


def _resolve_instance_names(request, instance_uuids):
    """Return a dict mapping instance_uuid -> instance name (or uuid if not found)."""
    if not instance_uuids:
        return {}
    uuid_to_name = {}
    try:
        servers, _more = api.nova.server_list(request, all_tenants=True)
        server_map = {s.id: s.name for s in servers}
        for iuid in instance_uuids:
            uuid_to_name[iuid] = server_map.get(iuid, iuid)
    except Exception:
        uuid_to_name = {u: u for u in instance_uuids}
    return uuid_to_name


def _build_device_usage(request, devices, deployables, arqs):
    """Set usage_display and attached_instances per device from deployables/ARQs.

    - rp_uuid (deployable) == device_rp_uuid (ARQ when bound)
    - deployable.device_id == device.id (internal id)
    """
    rp_to_device_id = {}
    for dep in (deployables or []):
        did = dep.get('device_id')
        rp = dep.get('rp_uuid')
        if did is not None and rp:
            rp_to_device_id[rp] = did

    device_id_to_instances = {}
    all_uuids = set()
    for arq in (arqs or []):
        rp = arq.get('device_rp_uuid')
        instance_uuid = arq.get('instance_uuid')
        if not rp or not instance_uuid:
            continue
        device_id = rp_to_device_id.get(rp)
        if device_id is None:
            continue
        all_uuids.add(instance_uuid)
        device_id_to_instances.setdefault(device_id, []).append(
            {'instance_uuid': instance_uuid})

    uuid_to_name = _resolve_instance_names(request, all_uuids)

    for device in (devices or []):
        device_id = device.get('id')
        raw_instances = device_id_to_instances.get(device_id, []) if device_id is not None else []
        instances = [
            {'instance_uuid': inst['instance_uuid'],
             'instance_name': uuid_to_name.get(inst['instance_uuid'], inst['instance_uuid'])}
            for inst in raw_instances
        ]
        device['attached_instances'] = instances
        device['usage_display'] = _("In Use") if instances else _("Available")
        device['attached_instances_display'] = (
            accelerator_tables.get_device_instance_link(device))
    return devices


class IndexView(tables.DataTableView):
    table_class = accelerator_tables.DevicesTable
    template_name = 'admin/accelerator/index.html'
    page_title = _("Accelerator")

    def get_data(self):
        try:
            devices = cyborg_api.device_list(self.request)
            deployables = []
            arqs = []
            try:
                deployables = cyborg_api.deployable_list(self.request)
            except Exception:
                exceptions.handle(self.request,
                                  _('Unable to retrieve deployables.'))
            try:
                arqs = cyborg_api.accelerator_request_list(self.request)
            except Exception:
                exceptions.handle(
                    self.request,
                    _('Unable to retrieve accelerator requests.'))
            return _build_device_usage(self.request, devices, deployables, arqs)
        except Exception:
            exceptions.handle(
                self.request,
                _('Unable to retrieve accelerator devices.'))
            return []
