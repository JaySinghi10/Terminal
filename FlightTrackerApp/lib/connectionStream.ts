// THE CONNECTION SEARCH, READ AS IT ARRIVES.
//
// expo/fetch, NOT THE GLOBAL fetch. React Native's own fetch buffers the whole
// body before resolving, so a streamed reply would arrive all at once at the
// end -- five seconds of nothing, then everything. Expo's fetch exposes the body
// as a ReadableStream. Its native module ships inside the core `expo` package
// (ExpoFetchModule, registered by expo's own module config), so every build of
// this app already contains it and no native rebuild was needed to use it.
//
// THE DECODER IS STREAMING, so a multi-byte character split across two chunks
// decodes once, whole. Expo's runtime installs a UTF-8 TextDecoder where the
// engine lacks one.
import { fetch as expoFetch } from 'expo/fetch';
import { lineSplitter, type ConnEvent } from './connections';

export async function streamConnections<L>(
  apiBase: string,
  origin: string,
  destination: string,
  day: string | null,
  auto: boolean,
  onEvent: (ev: ConnEvent<L>) => void,
  signal: AbortSignal,
): Promise<void> {
  const params = ['stream=1'];
  if (day !== null) params.push(`date=${day}`);
  // auto=1 lets the server decline when the month's units are low; see
  // connections.auto_allowed on the server.
  if (auto) params.push('auto=1');
  const response = await expoFetch(
    `${apiBase}/connections/${origin}/${destination}?${params.join('&')}`,
    { signal, headers: { Accept: 'application/x-ndjson' } },
  );
  if (!response.ok || response.body === null) {
    throw new Error(`connections: HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const split = lineSplitter();
  const emit = (text: string) => {
    for (const line of split(text)) {
      onEvent(JSON.parse(line) as ConnEvent<L>);
    }
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    emit(decoder.decode(value, { stream: true }));
  }
  emit(`${decoder.decode()}\n`);
}
