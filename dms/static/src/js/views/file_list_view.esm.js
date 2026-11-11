// /** ********************************************************************************
//     Copyright 2020 Creu Blanca
//     Copyright 2017-2019 MuK IT GmbH
//     Copyright 2024 Subteno - Timothée Vannier (https://www.subteno.com).
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/

import {
    createFileDropZoneExtension,
    createFileUploadExtension,
} from "./dms_file_upload.esm";
import {FileListController} from "./file_list_controller.esm";
import {FileListRenderer} from "./file_list_renderer.esm";
import {listView} from "@web/views/list/list_view";
import {patch} from "@web/core/utils/patch";
import {registry} from "@web/core/registry";

patch(FileListRenderer.prototype, createFileDropZoneExtension());
// Patch only the DMS controller: patching the global ListController overwrote
// `fileInput` in every list view (e.g. hr_expense's signal ref) and broke them.
patch(FileListController.prototype, createFileUploadExtension());
FileListRenderer.template = "dms.ListRenderer";

export const FileListView = {
    ...listView,
    Controller: FileListController,
    buttonTemplate: "dms.ListButtons",
    Renderer: FileListRenderer,
};

registry.category("views").add("file_list", FileListView);
