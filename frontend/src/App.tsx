import { DcView } from "./dc/DcView";
import { useMiCall } from "./logic/useMiCall";
import type { MiCallProps } from "./logic/MiCallLogic";
import template from "./app.template.html?raw";

// Default editor props from the prototype's data-props (theme/orbColor/aiName).
const DEFAULT_PROPS: MiCallProps = {
  theme: "light",
  orbColor: "#AAB8FF",
  aiName: "VEGAluo",
};

export default function App() {
  const logic = useMiCall(DEFAULT_PROPS);
  return <DcView template={template} vals={logic.renderVals()} />;
}
