/** @odoo-module **/

/**
 * Upload permission helpers for the DMS file views.
 *
 * Managers/administrators can upload anywhere. Other users can upload into the
 * folder they are browsing when that folder grants them the "Upload"
 * permission (directly or inherited from a parent folder). The server enforces
 * the same rule in dms.file.create(); this only decides whether to offer the
 * New / Upload buttons and the drop zone.
 */

export function dmsCurrentDirectoryId(searchModel) {
    if (!searchModel) {
        return false;
    }
    const category = searchModel.getSections?.()?.find((s) => s.fieldName === "directory_id");
    if (category?.activeValueId) {
        return category.activeValueId;
    }
    const domain =
        (typeof searchModel.getGlobalDomain === "function"
            ? searchModel.getGlobalDomain()
            : searchModel.domain) || [];
    for (const term of domain) {
        if (Array.isArray(term) && term[0] === "directory_id" && ["=", "child_of"].includes(term[1])) {
            const value = Array.isArray(term[2]) ? term[2][0] : term[2];
            if (Number.isInteger(value)) {
                return value;
            }
        }
    }
    return false;
}

export async function dmsCanUploadHere(orm, searchModel, isManager) {
    if (isManager) {
        return true;
    }
    const directoryId = dmsCurrentDirectoryId(searchModel);
    if (!directoryId) {
        return false;
    }
    try {
        const [rec] = await orm.read("dms.directory", [directoryId], ["permission_upload"]);
        return Boolean(rec?.permission_upload);
    } catch {
        return false;
    }
}
