'use client';

import React from 'react';

export class PanelBoundary extends React.Component<{ name: string; children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { console.error(`${this.props.name} panel failed`, error); }
  render() {
    if (this.state.failed) return <div role="alert" className="rounded-lg border border-warning/40 bg-warning/5 p-5 text-sm">{this.props.name} is temporarily unavailable. Core supply state remains authoritative.</div>;
    return this.props.children;
  }
}
