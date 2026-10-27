import { useEffect, useRef, useState } from "react";
import { Button, CircularProgress, Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import { useNavigate } from "react-router-dom";
import { OcrDocumentView, type OcrDocument as ViewDocument } from "../../vendor/react-form-builder";
import {
  acceptFor,
  describeDetection,
  describeFormats,
  formatsFor,
  isAccepted,
  useOcrFormatsQuery,
  useTemplateFromDocumentMutation,
  type OcrTemplate,
} from "../../api/ocr.api";
import { getApiErrorMessage } from "../../api/errors";
import { plainText } from "./layoutUtils";
// the detection preview's own styles and icons (this dialog also opens from the template list)
import "../../vendor/react-form-builder/scss/application.scss";
import "@fortawesome/fontawesome-free/css/all.min.css";
import "./designer.css";

/** What the designer opens with after an upload (passed in the router state). */
export interface ImportedTemplate {
  taskData: OcrTemplate["task_data"];
  fileName: string;
  /** The most prominent text on the form, as the template's title. */
  title: string;
  /** The uploaded document; a PDF or image is kept as the template's blank form. */
  file: File;
}

const RASTER = /\.(pdf|png|jpe?g)$/i;

/** Upload File (Template Builder): an Excel workbook, PDF or image of a form becomes an editable template. */
const UploadDocumentDialog = ({ open, onClose }: { open: boolean; onClose: () => void }) => {
  const navigate = useNavigate();
  const { data: formatInfo, isLoading: loadingFormats } = useOcrFormatsQuery(undefined, { skip: !open });
  const [convert, { isLoading: converting, reset }] = useTemplateFromDocumentMutation();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OcrTemplate | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const formats = formatsFor(formatInfo?.formats, "template");

  // a scan takes a while: show the seconds going by
  useEffect(() => {
    if (!converting) return;
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [converting]);

  const choose = (f?: File | null) => {
    setError(null);
    setResult(null);
    if (!f) return;
    if (formats.length && !isAccepted(f, formats)) {
      setFile(null);
      setError(`Please choose a supported file: ${describeFormats(formats)}.`);
      return;
    }
    setFile(f);
  };

  const run = async () => {
    if (!file) return;
    setError(null);
    setElapsed(0);
    try {
      setResult(await convert(file).unwrap());
    } catch (err) {
      setError(getApiErrorMessage(err, "The document could not be read."));
    }
  };

  const close = () => {
    setFile(null);
    setResult(null);
    setError(null);
    reset();
    onClose();
  };

  const openInDesigner = () => {
    if (!result || !file) return;
    const header = result.task_data.find((e) => e.element === "Header");
    const imported: ImportedTemplate = {
      taskData: result.task_data,
      fileName: file.name,
      title: result.title || plainText(header?.content) || file.name.replace(/\.[^.]+$/, ""),
      file,
    };
    close();
    navigate("/builder/new/build", { state: { imported } });
  };

  return (
    <Dialog open={open} onClose={converting ? undefined : close} fullWidth maxWidth={result ? "lg" : "sm"} className="upload-document-dialog rfb-scope">
      <div className="udd">
        <div className="udd-head">
          <div>
            <h2>Create a template from a document</h2>
            <p>
              Upload a blank (or filled) form as an Excel workbook, PDF or picture. Its text, labels, boxes to fill,
              tick boxes and ruled tables become editable fields.
            </p>
          </div>
          <IconButton aria-label="Close" onClick={close} disabled={converting}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </div>

        {!result && (
          <div
            className={`udd-drop${dragOver ? " over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              choose(e.dataTransfer.files?.[0]);
            }}
          >
            <UploadFileOutlinedIcon className="udd-drop-icon" />
            {file ? (
              <div className="udd-file">
                <InsertDriveFileOutlinedIcon fontSize="small" /> <b>{file.name}</b> ({Math.max(1, Math.round(file.size / 1024))} KB)
              </div>
            ) : (
              <div>Drop the file here, or</div>
            )}
            <Button size="small" variant="outlined" onClick={() => input.current?.click()} disabled={converting}>
              {file ? "Choose another file" : "Browse"}
            </Button>
            <input
              ref={input}
              type="file"
              hidden
              accept={acceptFor(formats)}
              aria-label="Document to convert"
              onChange={(e) => {
                choose(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <div className="udd-formats">
              {loadingFormats ? "Checking supported formats…" : `Supported: ${describeFormats(formats)}`}
              {formatInfo && !formatInfo.ocr_available && (
                <div className="udd-note">PDF and image reading is not installed on this server; Excel works.</div>
              )}
            </div>
          </div>
        )}

        {converting && (
          <div className="udd-progress" role="status">
            <CircularProgress size={18} />
            <span>
              Reading the document… {elapsed}s
              {file && RASTER.test(file.name) && " — scans are read with OCR, about 10–40 seconds a page."}
            </span>
          </div>
        )}
        {error && (
          <div className="udd-error" role="alert">
            {error}
          </div>
        )}

        {result && (
          <div className="udd-result">
            <div className="udd-summary">
              <b>{file?.name}</b>: {describeDetection(result.stats)} Check what was found, then open it in the designer
              to adjust the fields.
            </div>
            <div className="udd-preview ocr-scope">
              <OcrDocumentView document={result.document as unknown as ViewDocument} defaultMode="overlay" />
            </div>
          </div>
        )}

        <div className="udd-foot">
          <Button className="udd-cancel" onClick={close} disabled={converting}>
            Cancel
          </Button>
          {result ? (
            <Button variant="contained" className="udd-primary" onClick={openInDesigner} disabled={!result.task_data.length}>
              Open in designer
            </Button>
          ) : (
            <Button variant="contained" className="udd-primary" onClick={run} disabled={!file || converting}>
              {converting ? "Converting…" : "Convert"}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
};

export default UploadDocumentDialog;
