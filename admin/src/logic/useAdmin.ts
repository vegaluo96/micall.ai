import { useEffect, useRef, useState } from "react";
import { AdminLogic, type AdminProps } from "./AdminLogic";

/** Bridges the AdminLogic instance to React: setState schedules a re-render. */
export function useAdmin(props: AdminProps = {}): AdminLogic {
  const ref = useRef<AdminLogic | null>(null);
  const [, force] = useState(0);

  if (ref.current === null) {
    const logic = new AdminLogic(props);
    logic.attach(() => force((n) => n + 1));
    ref.current = logic;
  }

  useEffect(() => {
    const logic = ref.current!;
    void logic.componentDidMount();
    return () => logic.componentWillUnmount();
  }, []);

  return ref.current;
}
