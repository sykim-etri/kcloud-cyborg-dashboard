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

import logging

from django.utils.translation import gettext_lazy as _

from horizon import exceptions
from horizon import tables

from openstack_dashboard import api

from cyborg_dashboard.api import cyborg as cyborg_api
from cyborg_dashboard.content.admin.accelerator import tables as accel_tables
from cyborg_dashboard.content.admin.accelerator import usage as accel_usage

LOG = logging.getLogger(__name__)

USAGE_LABELS = {
    accel_usage.USAGE_IN_USE: _("In Use"),
    accel_usage.USAGE_AVAILABLE: _("Available"),
    accel_usage.USAGE_UNKNOWN: _("Unknown"),
}


def _resolve_instance_names(request, instance_uuids):
    """Map instance_uuid -> instance name, falling back to the uuid."""
    if not instance_uuids:
        return {}
    try:
        # all_tenants belongs in search_opts; passing it as a keyword raises
        # TypeError. detailed=False keeps the payload to id/name/links, which
        # is all this lookup needs.
        servers, _more = api.nova.server_list(
            request, search_opts={'all_tenants': True}, detailed=False)
    except Exception:
        # Names are cosmetic; degrade to uuids but do not hide the cause.
        LOG.exception("Unable to list instances to resolve accelerator "
                      "attachment names; falling back to uuids.")
        return {uuid: uuid for uuid in instance_uuids}

    # Instances in a down cell come back without a display name.
    server_map = {server.id: getattr(server, 'name', None) or server.id
                  for server in servers}
    unresolved = [uuid for uuid in instance_uuids if uuid not in server_map]
    if unresolved:
        # Deleted instances, or a server-side cap on the instance list. The
        # correlation itself is unaffected; only the label falls back.
        LOG.info("%d accelerator attachment(s) had no matching instance and "
                 "will display a uuid.", len(unresolved))
    return {uuid: server_map.get(uuid, uuid) for uuid in instance_uuids}


def _decorate(request, devices):
    """Attach display-ready instance tuples and a usage label."""
    uuid_to_name = _resolve_instance_names(
        request, accel_usage.collect_instance_uuids(devices))
    for device in devices:
        device['attached_instances'] = [
            {'instance_uuid': uuid,
             'instance_name': uuid_to_name.get(uuid, uuid)}
            for uuid in device.get('attached_instances') or []
        ]
        device['usage_display'] = USAGE_LABELS.get(
            device.get('usage'), USAGE_LABELS[accel_usage.USAGE_UNKNOWN])
    return devices


class IndexView(tables.DataTableView):
    table_class = accel_tables.DevicesTable
    template_name = 'admin/accelerator/index.html'
    page_title = _("Accelerator")

    def get_data(self):
        try:
            devices = cyborg_api.device_list(self.request)
        except Exception:
            exceptions.handle(
                self.request,
                _('Unable to retrieve accelerator devices.'))
            return []

        # Usage is only trustworthy when BOTH lookups succeed. A failed
        # lookup must not render a busy device as "Available".
        usage_known = True
        deployables = []
        arqs = []
        try:
            deployables = cyborg_api.deployable_list(self.request)
        except Exception:
            usage_known = False
            exceptions.handle(self.request,
                              _('Unable to retrieve deployables. Device '
                                'usage is shown as Unknown.'),
                              ignore=True)
        try:
            arqs = cyborg_api.accelerator_request_list(self.request)
        except Exception:
            usage_known = False
            exceptions.handle(self.request,
                              _('Unable to retrieve accelerator requests. '
                                'Device usage is shown as Unknown.'),
                              ignore=True)

        devices = accel_usage.correlate(devices, deployables, arqs,
                                        usage_known=usage_known)
        return _decorate(self.request, devices)
