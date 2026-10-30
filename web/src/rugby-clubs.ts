/** Real club marks from official sources. Provenance: docs/rugby-club-assets.md. */
export const rugbyClubs = [
  { id: 'toulouse', name: 'Stade Toulousain', shortName: 'Toulouse', logo: '/images/clubs/toulouse.png', source: 'https://top14.lnr.fr/club/toulouse' },
  { id: 'larochelle', name: 'Stade Rochelais', shortName: 'La Rochelle', logo: '/images/clubs/larochelle.png', source: 'https://top14.lnr.fr/club/la-rochelle' },
  { id: 'leinster', name: 'Leinster Rugby', shortName: 'Leinster', logo: '/images/clubs/leinster.png', source: 'https://www.leinsterrugby.ie/' },
  { id: 'racing92', name: 'Racing 92', shortName: 'Racing 92', logo: '/images/clubs/racing92.png', source: 'https://top14.lnr.fr/club/racing-92' },
  { id: 'toulon', name: 'RC Toulon', shortName: 'Toulon', logo: '/images/clubs/toulon.png', source: 'https://top14.lnr.fr/club/toulon' },
  { id: 'clermont', name: 'ASM Clermont Auvergne', shortName: 'Clermont', logo: '/images/clubs/clermont.png', source: 'https://top14.lnr.fr/club/clermont' },
  { id: 'munster', name: 'Munster Rugby', shortName: 'Munster', logo: '/images/clubs/munster.png', source: 'https://www.munsterrugby.ie/about-munster-rugby/munster-crest' },
  { id: 'crusaders', name: 'Crusaders', shortName: 'Crusaders', logo: '/images/clubs/crusaders.png', source: 'https://www.crusaders.co.nz/' },
] as const;

export type RugbyClub = typeof rugbyClubs[number];
export type RugbyClubId = RugbyClub['id'];
