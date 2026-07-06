import { useState } from 'react';

export default function CommandBar({ onSubmit, disabled }) {
  const [value, setValue] = useState('');

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue('');
  }

  return (
    <form className="command-bar" onSubmit={handleSubmit}>
      <input
        type="text"
        placeholder='Tell the agent what to do — e.g. "go to github.com/trending and tell me the page title"'
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
      />
      <button type="submit" disabled={disabled || !value.trim()}>
        {disabled ? 'Running…' : 'Run'}
      </button>
    </form>
  );
}
