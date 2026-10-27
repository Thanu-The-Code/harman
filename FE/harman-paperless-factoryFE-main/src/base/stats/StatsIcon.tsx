import React from "react";

/* Small inline illustrations (no image files needed).
   Swap with your own <img src="..."/> if you have the original assets. */

const DocBase: React.FC<{ accent: string; children: React.ReactNode }> = ({ accent, children }) => (
  <svg viewBox="0 0 76 68" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="20" y="4" width="50" height="54" rx="4" fill="#fff" stroke="#e5e7eb" />
    <rect x="28" y="12" width="28" height="3" rx="1.5" fill={accent} />
    <rect x="28" y="20" width="34" height="2" rx="1" fill="#d1d5db" />
    <rect x="28" y="27" width="34" height="2" rx="1" fill="#d1d5db" />
    <rect x="28" y="34" width="34" height="2" rx="1" fill="#d1d5db" />
    <rect x="28" y="41" width="22" height="2" rx="1" fill="#d1d5db" />
    {children}
  </svg>
);

const Badge: React.FC<{ color: string; children: React.ReactNode }> = ({ color, children }) => (
  <g>
    <rect x="8" y="38" width="22" height="22" rx="6" fill={color} stroke="#fff" strokeWidth="2" />
    {children}
  </g>
);

export const TotalDocIcon = () => (
  <svg viewBox="0 0 76 68" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="22" y="6" width="26" height="34" rx="3" fill="#fff" stroke="#e5e7eb" transform="rotate(-8 35 23)" />
    <rect x="36" y="4" width="26" height="34" rx="3" fill="#fff" stroke="#e5e7eb" transform="rotate(8 49 21)" />
    <rect x="28" y="12" width="20" height="2" rx="1" fill="#22c55e" />
    <rect x="28" y="18" width="24" height="2" rx="1" fill="#d1d5db" />
    <rect x="28" y="24" width="24" height="2" rx="1" fill="#d1d5db" />
    <rect x="8" y="30" width="60" height="32" rx="5" fill="#3fb8a9" />
    <path d="M8 35l30 18 30-18" stroke="#7fd6cb" strokeWidth="2" fill="none" />
  </svg>
);

export const VerificationIcon = () => (
  <DocBase accent="#22c55e">
    <Badge color="#22c55e">
      <path d="M14 49l4 4 7-8" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </Badge>
  </DocBase>
);

export const ChangeRequestIcon = () => (
  <DocBase accent="#f59e0b">
    <Badge color="#f59e0b">
      <circle cx="19" cy="49" r="5" stroke="#fff" strokeWidth="2" />
      <path d="M17 49h4M19 47v4" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
    </Badge>
  </DocBase>
);

export const DraftIcon = () => (
  <DocBase accent="#0ea5e9">
    <Badge color="#0ea5e9">
      <path d="M14 54l1-4 8-8 3 3-8 8-4 1z" fill="#fff" />
    </Badge>
  </DocBase>
);