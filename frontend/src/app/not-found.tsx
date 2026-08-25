import Link from 'next/link';

export default function NotFound() {
  return <main className="flex min-h-screen items-center justify-center bg-background"><div className="text-center"><p className="font-mono text-sm text-primary">404</p><h1 className="mt-3 text-3xl font-semibold">Page not found</h1><Link className="mt-5 inline-block text-primary underline" href="/">Return home</Link></div></main>;
}