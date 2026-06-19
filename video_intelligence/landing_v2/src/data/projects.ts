/** Sample projects for the Angus Emmerson-style video grid. Replace with your own. */
export interface Project {
  id: string
  title: string
  date: string
  videoSrc: string
  poster?: string
}

export const PROJECTS: Project[] = [
  {
    id: '1',
    title: '01',
    date: '2025',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
  },
  {
    id: '2',
    title: '02',
    date: '2025',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4',
  },
  {
    id: '3',
    title: '03',
    date: '2025',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4',
  },
  {
    id: '4',
    title: '04',
    date: '2025',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4',
  },
  {
    id: '5',
    title: '05',
    date: '2025',
    videoSrc: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerMeltdowns.mp4',
  },
]
