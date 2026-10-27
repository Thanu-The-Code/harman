import { Tab, Tabs } from "@mui/material";
import { customTabsStyles } from "./style";

export interface TabOption<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  tabs: TabOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}

function CustomTabs<T extends string>({ tabs, value, onChange, className }: Props<T>) {
  return (
    <Tabs
      className={className}
      sx={customTabsStyles}
      value={value}
      onChange={(_, v: T) => onChange(v)}
    >
      {tabs.map((t) => (
        <Tab key={t.value} className="custom-tab" value={t.value} label={t.label} />
      ))}
    </Tabs>
  );
}

export default CustomTabs;