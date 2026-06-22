import { DcView } from "./dc/DcView";
import { useAdmin } from "./logic/useAdmin";
import template from "./app.template.html?raw";

export default function App() {
  const logic = useAdmin();
  return <DcView template={template} vals={logic.renderVals()} />;
}
