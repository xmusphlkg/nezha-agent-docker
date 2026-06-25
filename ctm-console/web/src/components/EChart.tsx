import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { LineChart } from 'echarts/charts';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([GridComponent, LegendComponent, TooltipComponent, LineChart, CanvasRenderer]);

interface Props {
  option: echarts.EChartsCoreOption;
  height?: number;
}

export function EChart({ option, height = 260 }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const stableOption = useMemo(() => option, [option]);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current = echarts.init(ref.current, undefined, { renderer: 'canvas' });
    const resize = () => chartRef.current?.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(stableOption, true);
  }, [stableOption]);

  return <div className="chart" ref={ref} style={{ height }} />;
}
