# EH HR Compatibility

`eh_hr_compat`  -  Part of the EH HR Platform by ERP Heritage.

> Version compatibility shims for the EH HR Platform (Odoo 16/17/18/19).

HR Platform compatibility layer
This module is intentionally tiny. It contains NO business logic and NO state.
Its job is to normalise the parts of the Odoo API that change between minor
versions so the feature modules in eh_hr_platform/* can stay version-agnostic.

Public surface:
from odoo.addons.eh_hr_compat import CONTRACT_MODEL
from odoo.addons.eh_hr_compat import tracking
from odoo.addons.eh_hr_compat import legacy_view_mode
from odoo.addons.eh_hr_compat import owl_import_path
from odoo.addons.eh_hr_compat import safe_field_rename

Rules of engagement:
- No models defined here.
- No singletons, no caches, no global state.
- No imports from any other eh_hr_platform module.
- Anything that depends on the running Odoo version is resolved here once,
via odoo.release.version_info, and exposed as a constant.

## Dependencies

- Odoo: `base`

## Compatibility

Odoo 16, 17, 18 and 19 (Community). The module installs natively on 18 and 19; the 16 and 17 view layers are produced from the same source by `tools/backport_views.py`. The full platform test suite runs green on all four series.

## Licence

LGPL-3. Author: ERP Heritage.
