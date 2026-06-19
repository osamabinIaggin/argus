export interface Project {
  id: string
  title: string
  label: string
  videoSrc: string
  summary: string   // what the AI actually saw
}

export const PROJECTS: Project[] = [
  {
    id: '1',
    title: 'For Bigger Blazes',
    label: 'Game of Thrones · Chromecast',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
    summary:
      'Daenerys Targaryen and a fire-breathing dragon on a tablet screen. The shot cuts to the same dragon scene filling a full television tagged "For Bigger Blazes." A hand plugs a Chromecast dongle into the HDMI port, followed by HBO GO branding and the Google Chromecast logo and URL.',
  },
  {
    id: '2',
    title: 'For Bigger Meltdowns',
    label: 'Breaking Bad · Chromecast',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerMeltdowns.mp4',
    summary:
      'A man watches a video on a tablet. The content transitions to a large television overlaid with "Bigger Meltdowns." A hand inserts a Chrome device into the TV\'s HDMI port. Netflix branding and a $35 price point appear, closing on the full Chromecast logo and website.',
  },
  {
    id: '3',
    title: 'For Bigger Joyrides',
    label: 'Rally Car · Chromecast',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4',
    summary:
      'A finger taps a rally car video on a smartphone, which immediately expands to a full TV screen showing the car drifting through city streets alongside a trolley, captioned "Bigger Joyrides." A hand plugs a Chrome HDMI dongle into the TV, followed by YouTube on TV branding and pricing.',
  },
  {
    id: '4',
    title: 'For Bigger Escapes',
    label: 'Batman · Chromecast',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4',
    summary:
      'A person swipes through a technical schematic on a tablet, which explodes onto a large screen revealing a Batman motorcycle chase scene tagged "For Bigger Escapes." A hand inserts a Chromecast device into a TV\'s HDMI port, leading into promotional text screens and the Chromecast logo and URL.',
  },
  {
    id: '5',
    title: 'For Bigger Fun',
    label: 'Cricket Match · Chromecast',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4',
    summary:
      'A live cricket match plays on a tablet screen — players in white fielding across a stadium. The scene cuts to the same match filling a television captioned "For Bigger Fun." A Chromecast dongle is inserted into the HDMI port, closing on the Chromecast logo and promotional URL.',
  },
]
