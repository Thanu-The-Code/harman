import { useEffect, useRef, type CSSProperties } from "react";
import { AgCharts, AllCommunityModule, ModuleRegistry, type AgChartOptions } from "ag-charts-community";

ModuleRegistry.registerModules([AllCommunityModule]);

/**
 * An AG Chart, drawn afresh whenever its options change.
 *
 * Not ag-charts-react: that wrapper re-creates a chart in the same container element and
 * updates it in place, and AG Charts 14 then picks up the instance still attached to the
 * element - one already torn down (React StrictMode, a quick navigation) and frozen - which
 * throws on update or destroy. Here every chart gets its own new element and is only ever
 * created and destroyed.
 */
const Chart = ({ options, style }: { options: AgChartOptions; style?: CSSProperties }) => {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const parent = host.current;
    if (!parent) return;
    const container = document.createElement("div");
    container.style.width = "100%";
    container.style.height = "100%";
    parent.appendChild(container);
    const chart = AgCharts.create({ ...options, container });
    return () => {
      try {
        chart.destroy();
      } catch {
        /* already torn down; its element goes below either way */
      }
      container.remove();
    };
  }, [options]);

  return <div ref={host} style={style} />;
};

export default Chart;
