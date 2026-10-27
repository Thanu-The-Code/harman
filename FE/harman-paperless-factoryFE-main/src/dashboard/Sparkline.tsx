import { useMemo } from "react";
import Chart from "./Chart";
import type { AgCartesianChartOptions } from "ag-charts-community";

interface SparklineProps {
  data: number[];
  color: string;
}

export default function Sparkline({ data, color }: SparklineProps) {
 const options = useMemo<AgCartesianChartOptions>(
   () => ({
     data: data.map((v, i) => ({ i, v })),
     background: { visible: false },
     padding: { top: 2, right: 0, bottom: 0, left: 0 },
     legend: { enabled: false },
     tooltip: { enabled: false },
     series: [
       {
         type: "area",
         xKey: "i",
         yKey: "v",
         fill: color,
         fillOpacity: 0.18,
         stroke: color,
         strokeWidth: 1.5,
         marker: { enabled: false },
       },
     ],

     axes: {
       x: {
         type: "number",
         position: "bottom",
         label: { enabled: false },
         line: { enabled: false },
         tick: { enabled: false },
       },
       y: {
         type: "number",
         position: "left",
         label: { enabled: false },
         line: { enabled: false },
         tick: { enabled: false },
       },
     },
   }),
   [data, color],
 );

  return <Chart options={options} style={{ height: "100%", width: "100%" }} />;
}
