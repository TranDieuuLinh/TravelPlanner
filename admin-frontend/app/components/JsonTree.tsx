"use client";

import { useState } from "react";

export function JsonTree({
  data,
  name,
  isLast = true,
  isRoot = false,
  initiallyExpanded = true
}: {
  data: any;
  name?: string;
  isLast?: boolean;
  isRoot?: boolean;
  initiallyExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(initiallyExpanded);

  if (data === undefined) return null;

  if (typeof data === "object" && data !== null) {
    const isArray = Array.isArray(data);
    const keys = Object.keys(data);
    const openBrace = isArray ? "[" : "{";
    const closeBrace = isArray ? "]" : "}";

    if (keys.length === 0) {
      return (
        <div style={{ paddingLeft: isRoot ? 0 : 20, fontFamily: "var(--mono)", fontSize: "0.75rem", lineHeight: 1.6 }}>
          {name && <span className="json-key">"{name}": </span>}
          {openBrace}{closeBrace}{!isLast && ","}
        </div>
      );
    }

    return (
      <div style={{ paddingLeft: isRoot ? 0 : 20, fontFamily: "var(--mono)", fontSize: "0.75rem", lineHeight: 1.6 }}>
        <div
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(!expanded);
          }}
          style={{ cursor: "pointer", display: "inline-block", userSelect: "none" }}
        >
          <span style={{ display: "inline-block", width: 14, color: "var(--muted)", fontSize: "0.6rem", transform: "translateY(-1px)" }}>
            {expanded ? "▼" : "▶"}
          </span>
          {name && <span className="json-key">"{name}": </span>}
          <span style={{ color: "var(--text)" }}>{openBrace}</span>
          {!expanded && <span style={{ color: "var(--muted)" }}> {keys.length} {isArray ? "items" : "keys"} {closeBrace}{!isLast && ","}</span>}
        </div>
        
        {expanded && (
          <div>
            {keys.map((key, i) => (
              <JsonTree
                key={key}
                name={isArray ? undefined : key}
                data={(data as any)[key]}
                isLast={i === keys.length - 1}
                initiallyExpanded={initiallyExpanded}
              />
            ))}
            <div style={{ paddingLeft: 14, color: "var(--text)" }}>{closeBrace}{!isLast && ","}</div>
          </div>
        )}
      </div>
    );
  }

  let displayValue = "";
  let className = "json-string";
  if (typeof data === "string") {
    displayValue = `"${data.replace(/"/g, '\\"')}"`;
  } else if (typeof data === "number") {
    displayValue = String(data);
    className = "json-number";
  } else if (typeof data === "boolean") {
    displayValue = String(data);
    className = "json-boolean";
  } else if (data === null) {
    displayValue = "null";
    className = "json-null";
  } else {
    displayValue = String(data);
  }

  return (
    <div style={{ paddingLeft: isRoot ? 14 : 34, fontFamily: "var(--mono)", fontSize: "0.75rem", lineHeight: 1.6 }}>
      {name && <span className="json-key">"{name}": </span>}
      <span className={className}>{displayValue}</span>
      <span style={{ color: "var(--text)" }}>{!isLast && ","}</span>
    </div>
  );
}
