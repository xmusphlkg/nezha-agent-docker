import { Search, X } from 'lucide-react';

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function SearchInput({ value, onChange, placeholder = '搜索' }: Props) {
  return (
    <label className="search-input">
      <Search size={16} />
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
      {value && (
        <button type="button" onClick={() => onChange('')} title="清除搜索">
          <X size={14} />
        </button>
      )}
    </label>
  );
}
