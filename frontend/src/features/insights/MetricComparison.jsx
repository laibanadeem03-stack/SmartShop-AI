import { BarChart, Bar, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { chartRows, formatMetric, metricSummary, MODEL_COLORS, MODEL_LABELS, splitLabel } from './metricsPresentation.js';

export function MetricValue({ value, metric, exact = false }) {
  return <span className="metric-value"><data value={value == null ? '' : String(value)} title={value == null ? 'Not supplied by the API' : `API fraction: ${value}`}>{formatMetric(value,metric,exact)}</data>{exact && value != null && (metric === 'catalog_coverage_at_10' || metric.startsWith('fraction_')) && <small>API fraction: {String(value)}</small>}</span>;
}
function MetricTooltip({ active, payload, metric }) {
  const item = payload?.[0]?.payload;
  if (!active || !item) return null;
  return <div className="metric-tooltip" role="status" aria-live="polite" aria-atomic="true"><strong>{MODEL_LABELS[item.model]}</strong><span>{metric.title}: {formatMetric(item.raw,metric.key)}</span><small>API fraction: {String(item.raw)}</small></div>;
}
export function MetricComparison({ metric, rows, split, exact }) {
  const data = chartRows(rows,metric.key), id = `metric-${metric.key}`;
  const hasValues = data.some(row => row.value != null);
  const coverage = metric.key === 'catalog_coverage_at_10';
  return <article className="metric-comparison" data-metric={metric.key}>
    <div className="metric-comparison-heading"><h3 id={`${id}-heading`}>{metric.title}</h3><span>{metric.unit}</span></div>
    <figure aria-labelledby={`${id}-heading`} aria-describedby={`${id}-summary`}>
      {hasValues ? <div className="comparison-chart"><ResponsiveContainer width="100%" height={234} minWidth={0} initialDimension={{width:330,height:234}}>
        <BarChart data={data} margin={{top:16,right:10,left:0,bottom:0}} accessibilityLayer tabIndex={0} aria-label={`${metric.title}, ${splitLabel(split)} overall. Use Left and Right arrow keys to inspect model values.`} aria-describedby={`${id}-summary`}>
          <CartesianGrid vertical={false} stroke="#edf0f5" />
          <XAxis dataKey="name" tick={{fontSize:10,fill:'#526078'}} tickLine={false} axisLine={false} interval={0} height={30} />
          <YAxis domain={coverage ? [0,100] : [0,'auto']} width={56} tick={{fontSize:10,fill:'#526078'}} tickLine={false} axisLine={false} tickFormatter={value => coverage ? `${value}%` : Number(value.toPrecision(3)).toString()} />
          <Tooltip content={<MetricTooltip metric={metric}/>} isAnimationActive={false} cursor={{fill:'#f5f7fb'}} />
          <Bar dataKey="value" name={metric.title} radius={[5,5,0,0]} maxBarSize={46} isAnimationActive={false}>{data.map(row => <Cell key={row.model} fill={MODEL_COLORS[row.model]} />)}</Bar>
        </BarChart>
      </ResponsiveContainer></div> : <p className="chart-empty">No values were supplied for this metric.</p>}
      <figcaption id={`${id}-summary`}>{metricSummary(rows,metric.key,split)} All axes start at zero.</figcaption>
    </figure>
    <div className="insights-table-wrap"><table className="metric-data-table"><caption>{metric.title} — {splitLabel(split)}, overall. Equivalent chart data.</caption><thead><tr><th scope="col">Model</th><th scope="col">{coverage ? 'Coverage (%)' : metric.title}</th></tr></thead><tbody>{rows.map(row => <tr key={row.model}><th scope="row"><span className="model-dot" style={{background:MODEL_COLORS[row.model]}} aria-hidden="true" />{MODEL_LABELS[row.model]}</th><td><MetricValue value={row.overall?.[metric.key]} metric={metric.key} exact={exact}/></td></tr>)}</tbody></table></div>
  </article>;
}
