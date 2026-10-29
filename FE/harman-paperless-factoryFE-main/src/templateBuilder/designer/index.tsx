import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Button, Dialog, IconButton, Tooltip } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import CloseIcon from "@mui/icons-material/Close";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "react-toastify";
import { BuilderProvider, ReactFormGenerator, Registry, Toolbar } from "../../vendor/react-form-builder";
import "../../vendor/react-form-builder/scss/application.scss";
// the icons the builder draws on each element (edit / delete / drag, ✓ cells)
import "@fortawesome/fontawesome-free/css/all.min.css";
import "./designer.css";
import TableGrid from "./TableGrid";
import DesignerCanvas from "./DesignerCanvas";
import FieldProperties from "./FieldProperties";
import TextToolbar from "./TextToolbar";
import TemplateDetailsDialog, { type TemplateDetails } from "./TemplateDetailsDialog";
import ProcessStep from "./ProcessStep";
import SubmitApprovalDialog from "./SubmitApprovalDialog";
import type { ImportedTemplate } from "./UploadDocumentDialog";
import type { Responsibilities } from "./ResponsibilitiesPanel";
import { PALETTE } from "./palette";
import { useLayoutHistory } from "./useLayoutHistory";
import { designerStyles } from "./style";
import CustomDialog from "../../base/dialog/CustomDialog";
import { ErrorState, PageLoader } from "../../base/feedback";
import { retryUnlessFinal } from "../../base/feedback/retry";
import {
  formatStatusLabel,
  useCreateFormatMutation,
  useFormatTeamsQuery,
  useGetFormatQuery,
  usePublishWithoutApprovalMutation,
  useTemplateFoldersQuery,
  useUpdateFormatMutation,
  useUploadBlankMutation,
  type FormatDetail,
  type FormatPayload,
  type LayoutItem,
} from "../../api/formats.api";
import { getApiErrorMessage } from "../../api/errors";

// Templates made with the earlier table element still open: the builder looks it up by key.
// (react-form-builder types the argument as a component; TableGrid is one, with a ref)
if (!Registry.list().includes("TableGrid")) Registry.register("TableGrid", TableGrid as never);

type Step = "design" | "process";

const NEW_RESPONSIBILITIES: Responsibilities = {
  frequency: "daily",
  process_owner_id: "",
  overall_process_owner_id: "",
  qms_coordinator_id: "",
  cft_member_ids: [],
  cft_target_days: 3,
  work_instruction_ref: "",
  work_instruction: "",
  storage_path: "",
};

const responsibilitiesOf = (f?: FormatDetail): Responsibilities =>
  f
    ? {
        frequency: f.frequency,
        process_owner_id: f.process_owner?.id ?? "",
        overall_process_owner_id: f.overall_process_owner?.id ?? "",
        qms_coordinator_id: f.qms_coordinator?.id ?? "",
        cft_member_ids: f.cft_members.map((m) => m.id),
        cft_target_days: f.cft_target_days || 3,
        work_instruction_ref: f.work_instruction_ref ?? "",
        work_instruction: f.work_instruction ?? "",
        storage_path: f.storage_path ?? "",
      }
    : NEW_RESPONSIBILITIES;

const orNull = (value: string) => value.trim() || null;

/** A layout item as saved: without the builder's "being edited" flag. */
const withoutEditState = (item: LayoutItem): LayoutItem => {
  const copy = { ...item };
  delete copy.dirty;
  return copy;
};
const RASTER = /\.(pdf|png|jpe?g)$/i;

/* ------------------------------------------------------------------ editor */

interface EditorProps {
  format?: FormatDetail; // undefined = a new template
  imported?: ImportedTemplate; // a new template made from an uploaded document
  step: Step;
}

function TemplateEditor({ format, imported, step }: EditorProps) {
  const navigate = useNavigate();
  const { data: teamsData } = useFormatTeamsQuery();
  const { data: foldersData } = useTemplateFoldersQuery();
  const [createFormat, { isLoading: creating }] = useCreateFormatMutation();
  const [updateFormat, { isLoading: updating }] = useUpdateFormatMutation();
  const [publish, { isLoading: publishing }] = usePublishWithoutApprovalMutation();
  const [uploadBlank] = useUploadBlankMutation();

  // a copy: the builder writes into its items (`component`, `dirty`), and RTK Query data is frozen
  const initialLayout = useMemo<LayoutItem[]>(
    () => structuredClone(Array.isArray(format?.layout) ? format.layout : (imported?.taskData ?? [])),
    [format, imported],
  );
  const [layout, setLayout] = useState<LayoutItem[]>(initialLayout);
  const [details, setDetails] = useState<TemplateDetails>(() => ({
    title: format?.title ?? imported?.title ?? "",
    code: format?.code ?? "",
    description: format?.description ?? "",
    teamId: format?.team?.id ?? "",
    folder: format?.storage_path ?? "",
  }));
  const [resp, setResp] = useState<Responsibilities>(() => responsibilitiesOf(format));
  const [selected, setSelected] = useState<LayoutItem | null>(null);
  const [panel, setPanel] = useState<"fields" | "properties">("fields");
  const [propertiesEl, setPropertiesEl] = useState<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(100);
  // a new template from a document asks for its details straight away
  const [dialog, setDialog] = useState<"details" | "preview" | "submit" | "publish" | null>(imported ? "details" : null);
  const [afterDetails, setAfterDetails] = useState<"save" | "continue" | null>(null);
  // the template as just saved: the approval dialog proposes its QMS Coordinator
  const [toSubmit, setToSubmit] = useState<FormatDetail | null>(null);
  const history = useLayoutHistory();

  const editable = !format || format.status === "draft";
  const saving = creating || updating;
  const teams = (teamsData?.teams ?? []).filter((t) => t.is_active || t.id === details.teamId);

  useEffect(() => {
    window.scrollTo(0, 0);
    history.record(initialLayout);
    // once, with the starting layout
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the browser back gesture from accidentally closing the designer while editing.
  // The explicit Back button still provides the intentional way to leave this screen.
  useEffect(() => {
    const keepDesignerOpen = () => {
      window.history.pushState(null, document.title, window.location.href);
    };

    window.history.pushState(null, document.title, window.location.href);
    window.addEventListener("popstate", keepDesignerOpen);
    return () => window.removeEventListener("popstate", keepDesignerOpen);
  }, []);

  const { record } = history;
  const onCanvasChange = useCallback(
    (data: LayoutItem[]) => {
      setLayout(data);
      record(data);
    },
    [record],
  );

  const onSelect = (element: LayoutItem | null) => {
    setSelected(element);
    if (element) setPanel("properties");
  };

  const payload = (d: TemplateDetails): FormatPayload => ({
    code: d.code.trim().toUpperCase(),
    title: d.title.trim(),
    description: orNull(d.description),
    team_id: d.teamId,
    frequency: resp.frequency,
    layout: layout.map(withoutEditState),
    fields: [], // the layout is the source of truth; the server derives the fields
    process_owner_id: resp.process_owner_id || null,
    overall_process_owner_id: resp.overall_process_owner_id || null,
    qms_coordinator_id: resp.qms_coordinator_id || null,
    cft_member_ids: resp.cft_member_ids,
    cft_target_days: resp.cft_target_days,
    work_instruction_ref: orNull(resp.work_instruction_ref),
    work_instruction: orNull(resp.work_instruction),
    // the folder chosen in the details is the template's folder in the library (and its filing root)
    storage_path: orNull(d.folder),
  });

  /** Save the draft; returns the saved template, or null (details missing or the save failed). */
  const save = async (next: "save" | "continue", d = details): Promise<FormatDetail | null> => {
    if (!d.title.trim() || !d.teamId) {
      setAfterDetails(next);
      setDialog("details");
      return null;
    }
    // a blank code is given the team's next one by the server
    const withCode = d;
    try {
      if (format) {
        const saved = await updateFormat({ id: format.id, ...payload(withCode) }).unwrap();
        if (next === "save") toast.success("Draft saved.");
        else navigate(`/builder/${format.id}/build?format_id=${format.id}&step=process`);
        return saved;
      }
      const created = await createFormat(payload(withCode)).unwrap();
      // the uploaded scan / PDF becomes the blank form people can print
      if (imported && RASTER.test(imported.fileName)) {
        await uploadBlank({ id: created.id, file: imported.file })
          .unwrap()
          .catch(() => toast.warn("The template was saved, but its blank form could not be attached."));
      }
      toast.success("Template created as a draft.");
      navigate(`/builder/${created.id}/build?format_id=${created.id}${next === "continue" ? "&step=process" : ""}`, { replace: true });
      return created;
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Something went wrong while saving the form."));
      return null;
    }
  };

  const submitDetails = async (d: TemplateDetails) => {
    setDetails(d);
    setDialog(null);
    const next = afterDetails;
    setAfterDetails(null);
    if (next) await save(next, d);
    else if (format) await save("save", d);
  };

  const handleSendForApproval = async () => {
    const saved = await save("save");
    if (!saved) return;
    if (saved.readiness.length) {
      toast.error("Fix the items listed under “Before this template can be released”.");
      return;
    }
    setToSubmit(saved);
    setDialog("submit");
  };

  const handlePublish = async () => {
    setDialog(null);
    const saved = await save("save");
    if (!saved || !format) return;
    try {
      await publish(format.id).unwrap();
      toast.success("Template released without approval (recorded in the audit log).");
      navigate(`/builder/${format.id}`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Unable to release the template."));
    }
  };

  const status = format ? formatStatusLabel(format.status, format.approval_status) : null;
  const title = details.title.trim() || "Untitled";
  const editingDesign = editable && step === "design";
  const back = () =>
    step === "process" && format
      ? navigate(`/builder/${format.id}/build?format_id=${format.id}`)
      : navigate(format ? `/builder/${format.id}` : "/builder");

  return (
    <Box className={`designer-page rfb-scope${editingDesign ? " designer-page-editing" : ""}`} sx={designerStyles}>
      <div className="designer-topbar">
        <div className="designer-title">
          <IconButton className="back-btn" aria-label="Back" onClick={back}>
            <ChevronLeftIcon />
          </IconButton>
          <h1 title={title}>{title}</h1>
          {editable && (
            <Button className="edit-details-btn" startIcon={<EditOutlinedIcon fontSize="small" />} onClick={() => setDialog("details")}>
              Edit
            </Button>
          )}
          {status && <span className={`status-chip ${format?.status ?? ""} ${format?.approval_status ?? ""}`}>{status}</span>}
          {format && <span className="muted code-chip">{format.code} · rev {format.revision}</span>}
        </div>
        <div className="designer-actions">
          {step === "design" ? (
            <>
              <Tooltip title="Preview the form">
                <IconButton className="preview-btn" aria-label="Preview" onClick={() => setDialog("preview")}>
                  <VisibilityOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Button className="btn-soft" disabled={!editable || saving} onClick={() => save("save")}>
                {saving ? "Saving…" : "Save Draft"}
              </Button>
              <Button className="btn-primary" variant="contained" disabled={!editable || saving} onClick={() => save("continue")}>
                Continue
              </Button>
            </>
          ) : (
            <>
              <Button className="btn-soft" onClick={back}>
                Back to design
              </Button>
              <Button className="btn-soft" disabled={!editable || saving} onClick={() => save("save")}>
                {saving ? "Saving…" : "Save Draft"}
              </Button>
              {format?.status === "draft" && (
                <>
                  <Button className="btn-soft" disabled={publishing} onClick={() => setDialog("publish")}>
                    Publish without approval
                  </Button>
                  <Button className="btn-primary" variant="contained" disabled={saving} onClick={handleSendForApproval}>
                    Send for approval
                  </Button>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {!editable && format && (
        <div className="notice info">
          This template is {String(status).toLowerCase()} and can no longer be edited here. A released template changes
          through a Change Request, which creates a new revision.
        </div>
      )}
      {format?.approval_status === "rejected" && (
        <div className="notice warn">
          The last approval was rejected. Address the reviewers' comments on the template page, save, and send it again.
        </div>
      )}
      {editable && format && format.readiness.length > 0 && (
        <div className="notice warn">
          <div>
            <strong>Before this template can be released</strong>
            <ul>
              {format.readiness.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {step === "process" && format ? (
        <ProcessStep format={format} value={resp} onChange={(patch) => setResp((r) => ({ ...r, ...patch }))} disabled={!editable} />
      ) : !editable ? (
        <div className="designer-readonly">
          <ReactFormGenerator form_action="" form_method="POST" data={initialLayout} read_only hide_actions />
        </div>
      ) : (
        <BuilderProvider>
          <TextToolbar
            selected={selected}
            undo={history.undo}
            redo={history.redo}
            canUndo={history.canUndo}
            canRedo={history.canRedo}
            zoom={zoom}
            onZoom={setZoom}
            onFieldSettings={() => setPanel("properties")}
          />
          <div className="designer-workspace">
            <div className="designer-canvas">
              <DesignerCanvas
                initialData={initialLayout}
                onChange={onCanvasChange}
                propertiesContainer={propertiesEl}
                renderProperties={(props) => <FieldProperties key={String(props.element?.id)} {...props} />}
                onSelect={onSelect}
                zoom={zoom}
              />
            </div>
            <aside className="designer-panel" aria-label="Fields">
              <div className="panel-tabs" role="tablist">
                <button type="button" role="tab" aria-selected={panel === "fields"} className={panel === "fields" ? "active" : ""} onClick={() => setPanel("fields")}>
                  Add Fields
                </button>
                <button type="button" role="tab" aria-selected={panel === "properties"} className={panel === "properties" ? "active" : ""} onClick={() => setPanel("properties")}>
                  Field Properties
                </button>
              </div>
              <div className="panel-body" hidden={panel !== "fields"}>
                <Toolbar items={PALETTE} layout="tiles" />
              </div>
              {/* the selected element's properties are drawn into this box by the canvas */}
              <div className="panel-body" hidden={panel !== "properties"}>
                {!selected && <p className="panel-empty">Select a field on the page to see and change its properties.</p>}
                <div ref={setPropertiesEl} />
              </div>
            </aside>
          </div>
        </BuilderProvider>
      )}

      {dialog === "details" && (
        <TemplateDetailsDialog
          open
          mode={format ? "edit" : "create"}
          initial={details}
          teams={teams}
          folders={foldersData?.folders ?? []}
          busy={saving}
          onClose={() => {
            setDialog(null);
            setAfterDetails(null);
          }}
          onSubmit={submitDetails}
        />
      )}

      <Dialog open={dialog === "preview"} onClose={() => setDialog(null)} fullWidth maxWidth="md" className="designer-preview-dialog rfb-scope">
        <div className="dpd-head">
          <h2>{title}</h2>
          <IconButton aria-label="Close preview" onClick={() => setDialog(null)}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </div>
        <div className="dpd-body">
          {dialog === "preview" && <ReactFormGenerator form_action="" form_method="POST" data={structuredClone(layout)} hide_actions />}
        </div>
      </Dialog>

      {toSubmit && dialog === "submit" && (
        <SubmitApprovalDialog
          open
          format={toSubmit}
          onClose={() => setDialog(null)}
          onSubmitted={() => {
            setDialog(null);
            navigate(`/builder/${toSubmit.id}`);
          }}
        />
      )}
      <CustomDialog
        open={dialog === "publish"}
        onClose={() => setDialog(null)}
        onConfirm={handlePublish}
        title="Publish without approval?"
        subtitle="The template is released straight into the Resources library. The bypass is recorded in the audit log."
        confirmText="Publish"
      >
        <p style={{ margin: 0, fontSize: 13 }}>Use this only where the template has been approved outside the system.</p>
      </CustomDialog>
    </Box>
  );
}

/* -------------------------------------------------------------------- page */

function BuildTemplate() {
  const [searchParams] = useSearchParams();
  const { state } = useLocation();
  const formatId = searchParams.get("format_id");
  const step: Step = searchParams.get("step") === "process" && formatId ? "process" : "design";
  const { data: format, isLoading, isError, error, refetch } = useGetFormatQuery(formatId ?? "", { skip: !formatId });
  const imported = formatId ? undefined : (state as { imported?: ImportedTemplate } | null)?.imported;

  if (formatId && isLoading) return <PageLoader label="Loading form builder…" />;
  if (formatId && (isError || !format)) {
    return <ErrorState message={(error && "message" in error && error.message) || "Unable to load the form."} onRetry={retryUnlessFinal(error, refetch)} />;
  }
  // keyed so the editor's state starts from the loaded template
  return <TemplateEditor key={format?.id ?? "new"} format={format} imported={imported} step={step} />;
}

export default BuildTemplate;
