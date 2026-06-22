import { useEffect, useRef, useState } from "react";
import { MiCallLogic, type MiCallProps } from "./MiCallLogic";

/** Bridges the (framework-agnostic) MiCallLogic instance to React: setState on
 *  the logic schedules a re-render, mirroring DCLogic's host wiring. */
export function useMiCall(props: MiCallProps): MiCallLogic {
  const ref = useRef<MiCallLogic | null>(null);
  const [, force] = useState(0);

  if (ref.current === null) {
    const logic = new MiCallLogic(props);
    logic.attach(() => force((n) => n + 1));
    ref.current = logic;
  }

  useEffect(() => {
    const logic = ref.current!;
    logic.componentDidMount();
    return () => logic.componentWillUnmount();
  }, []);

  return ref.current;
}
