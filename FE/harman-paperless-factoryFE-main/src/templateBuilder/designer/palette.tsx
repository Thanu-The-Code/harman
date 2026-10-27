import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import TitleOutlinedIcon from "@mui/icons-material/TitleOutlined";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";
import FormatTextdirectionLToROutlinedIcon from "@mui/icons-material/FormatTextdirectionLToROutlined";
import HorizontalRuleOutlinedIcon from "@mui/icons-material/HorizontalRuleOutlined";
import ArrowDropDownCircleOutlinedIcon from "@mui/icons-material/ArrowDropDownCircleOutlined";
import LocalOfferOutlinedIcon from "@mui/icons-material/LocalOfferOutlined";
import LibraryAddCheckOutlinedIcon from "@mui/icons-material/LibraryAddCheckOutlined";
import RadioButtonCheckedOutlinedIcon from "@mui/icons-material/RadioButtonCheckedOutlined";
import ShortTextOutlinedIcon from "@mui/icons-material/ShortTextOutlined";
import EmailOutlinedIcon from "@mui/icons-material/EmailOutlined";
import PhoneOutlinedIcon from "@mui/icons-material/PhoneOutlined";
import AddOutlinedIcon from "@mui/icons-material/AddOutlined";
import SubjectOutlinedIcon from "@mui/icons-material/SubjectOutlined";
import ListAltOutlinedIcon from "@mui/icons-material/ListAltOutlined";
import ViewColumnOutlinedIcon from "@mui/icons-material/ViewColumnOutlined";
import CalendarMonthOutlinedIcon from "@mui/icons-material/CalendarMonthOutlined";
import DrawOutlinedIcon from "@mui/icons-material/DrawOutlined";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import StarBorderOutlinedIcon from "@mui/icons-material/StarBorderOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import AttachFileOutlinedIcon from "@mui/icons-material/AttachFileOutlined";
import PhotoCameraOutlinedIcon from "@mui/icons-material/PhotoCameraOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import type { PaletteItem } from "../../vendor/react-form-builder";

/**
 * The designer's "Add Fields" palette (Figma: Document create). Each entry names a
 * builder element; the builder fills in the rest of its defaults by key.
 */

const BASIC = "Basic Fields";
const LAYOUT = "Layout Fields";
const ADVANCED = "Advanced Fields";

const icon = (Icon: typeof AddOutlinedIcon) => <Icon fontSize="small" />;

export const PALETTE: PaletteItem[] = [
  {
    key: "Table",
    name: "Table/Grid",
    group_name: BASIC,
    iconNode: icon(TableChartOutlinedIcon),
    label: "Table",
    // a small ruled table to start from: a printed column, a reading and an OK / N-OK tick
    columns: [{ text: "Check point" }, { text: "Reading" }, { text: "OK / N-OK" }],
    rows: [
      { cells: [{ text: "Item 1" }, { input: "number" }, { input: "check" }] },
      { cells: [{ text: "Item 2" }, { input: "number" }, { input: "check" }] },
    ],
  },
  { key: "Header", name: "Header Text", group_name: BASIC, iconNode: icon(TitleOutlinedIcon), content: "Heading" },
  { key: "Label", name: "Label", group_name: BASIC, iconNode: icon(TextFieldsOutlinedIcon), content: "Label" },
  { key: "Paragraph", name: "Paragraph", group_name: BASIC, iconNode: icon(FormatTextdirectionLToROutlinedIcon), content: "Paragraph text" },
  { key: "LineBreak", name: "Line Break", group_name: BASIC, iconNode: icon(HorizontalRuleOutlinedIcon) },
  { key: "Dropdown", name: "Dropdown", group_name: BASIC, iconNode: icon(ArrowDropDownCircleOutlinedIcon), label: "Dropdown" },
  { key: "Tags", name: "Tags", group_name: BASIC, iconNode: icon(LocalOfferOutlinedIcon), label: "Tags" },
  { key: "Checkboxes", name: "Checkboxes", group_name: BASIC, iconNode: icon(LibraryAddCheckOutlinedIcon), label: "Checkboxes" },
  { key: "RadioButtons", name: "Multiple Choice", group_name: BASIC, iconNode: icon(RadioButtonCheckedOutlinedIcon), label: "Multiple choice" },
  { key: "TextInput", name: "Text Input", group_name: BASIC, iconNode: icon(ShortTextOutlinedIcon), label: "Text" },
  { key: "EmailInput", name: "Email", group_name: BASIC, iconNode: icon(EmailOutlinedIcon), label: "Email" },
  { key: "PhoneNumber", name: "Phone Number", group_name: BASIC, iconNode: icon(PhoneOutlinedIcon), label: "Phone number" },
  { key: "NumberInput", name: "Number Input", group_name: BASIC, iconNode: icon(AddOutlinedIcon), label: "Number" },
  { key: "TextArea", name: "Multi-line Input", group_name: BASIC, iconNode: icon(SubjectOutlinedIcon), label: "Notes" },
  { key: "FieldSet", name: "Field Set", group_name: BASIC, iconNode: icon(ListAltOutlinedIcon) },

  { key: "TwoColumnRow", name: "Two Column Row", group_name: LAYOUT, iconNode: icon(ViewColumnOutlinedIcon) },
  { key: "ThreeColumnRow", name: "Three Column Row", group_name: LAYOUT, iconNode: icon(ViewColumnOutlinedIcon) },
  { key: "FourColumnRow", element: "MultiColumnRow", name: "Four Column Row", group_name: LAYOUT, iconNode: icon(ViewColumnOutlinedIcon) },
  { key: "FiveColumnRow", element: "MultiColumnRow", name: "Five Column Row", group_name: LAYOUT, iconNode: icon(ViewColumnOutlinedIcon) },
  { key: "SixColumnRow", element: "MultiColumnRow", name: "Six Column Row", group_name: LAYOUT, iconNode: icon(ViewColumnOutlinedIcon) },

  { key: "DatePicker", name: "Date", group_name: ADVANCED, iconNode: icon(CalendarMonthOutlinedIcon), label: "Date" },
  { key: "Signature", name: "Signature", group_name: ADVANCED, iconNode: icon(DrawOutlinedIcon), label: "Signature" },
  { key: "Image", name: "Image", group_name: ADVANCED, iconNode: icon(ImageOutlinedIcon) },
  { key: "Rating", name: "Rating", group_name: ADVANCED, iconNode: icon(StarBorderOutlinedIcon), label: "Rating" },
  { key: "Range", name: "Range", group_name: ADVANCED, iconNode: icon(TuneOutlinedIcon), label: "Range" },
  { key: "HyperLink", name: "Website", group_name: ADVANCED, iconNode: icon(LinkOutlinedIcon) },
  { key: "Download", name: "File Attachment", group_name: ADVANCED, iconNode: icon(AttachFileOutlinedIcon) },
  { key: "Camera", name: "Camera", group_name: ADVANCED, iconNode: icon(PhotoCameraOutlinedIcon), label: "Photo" },
  { key: "FileUpload", name: "File Upload", group_name: ADVANCED, iconNode: icon(UploadFileOutlinedIcon), label: "File" },
];

/** The palette's name for an element on the canvas ("Dropdown Field"). */
export const elementTitle = (item: { element?: unknown; key?: unknown }) => {
  const key = String(item.element === "MultiColumnRow" ? item.key : item.element ?? "");
  const found = PALETTE.find((p) => p.key === key || p.element === key);
  if (found) return found.name;
  if (item.element === "CustomElement" && item.key === "TableGrid") return "Table/Grid (earlier)";
  return key.replace(/([a-z])([A-Z])/g, "$1 $2");
};
