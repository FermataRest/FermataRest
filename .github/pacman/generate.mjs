import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';

// Use the library directly: the upstream Action wrapper also reports analytics.
export function renderSvg(Renderer, { username, token, theme }) {
  return new Promise((resolveSvg, reject) => {
    let svg;
    const renderer = new Renderer({
      game: 'pacman',
      platform: 'github',
      username,
      gameTheme: theme,
      playerStyle: 'opportunistic',
      showMonthLabels: true,
      githubSettings: { accessToken: token },
      svgCallback: (value) => { svg = value; },
      gameOverCallback: () => {
        if (typeof svg !== 'string' || !svg.includes('<svg')) {
          reject(new Error(`Pac-Man did not produce an SVG for ${theme}`));
          return;
        }
        resolveSvg(svg);
      },
    });
    Promise.resolve(renderer.start()).catch(reject);
  });
}

export async function generateGraphs({
  username = process.env.GITHUB_PROFILE_USERNAME || 'FermataRest',
  token = process.env.GITHUB_TOKEN,
  outputDir = 'dist',
  Renderer,
  log = console.log,
} = {}) {
  if (typeof token !== 'string' || !token.trim()) {
    throw new Error('GITHUB_TOKEN is required to read the contribution calendar');
  }
  if (typeof username !== 'string' || !username.trim()) {
    throw new Error('A GitHub profile username is required');
  }
  if (!Renderer) {
    // The workflow downloads and checksum-verifies this pinned library first.
    ({ ArcadeRenderer: Renderer } = await import('./pacman-library.mjs'));
  }

  await mkdir(outputDir, { recursive: true });
  const paths = [];
  for (const [theme, filename] of [
    ['github', 'pacman-contribution-graph.svg'],
    ['github-dark', 'pacman-contribution-graph-dark.svg'],
  ]) {
    const svg = await renderSvg(Renderer, { username: username.trim(), token, theme });
    const path = join(outputDir, filename);
    await writeFile(path, svg, 'utf8');
    paths.push(path);
    log(`Generated ${filename}`);
  }
  return paths;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  generateGraphs().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
