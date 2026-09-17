/* Mermaid is owned by Material, not this site.
 *
 * Material renders pre.mermaid into a closed shadow root on document$ and
 * themes it with --md-mermaid-* custom properties. The former renderer here
 * raced it, then read empty textContent from that shadow host as diagram
 * source. mermaid.run() rejected asynchronously (a synchronous try/catch
 * could not catch it). Palette changes repeated the race.
 *
 * Intentionally no listeners, polling, global mermaid.initialize(), or run().
 * Keep this compatibility stub for cached configurations. New configurations
 * should omit this file AND the separate Mermaid CDN script; Material loads
 * its supported version only on pages with diagrams.
 */
