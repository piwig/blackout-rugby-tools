export const stadiumCategories=['standing','uncovered','covered','members','corporate'] as const;
export const stadiumRatios=[22,39,30,8,1];

// Use the decimal input, as the server does. Binary 25 * 5.1 is just below
// 127.5 in JavaScript and would otherwise round down to 127 instead of 128.
const fraction=(value:number):[bigint,bigint]=>{
  const [mantissa,exponent='0']=String(value).toLowerCase().split('e');
  const [whole,decimal='']=mantissa.split('.');
  const scale=decimal.length-Number(exponent),digits=BigInt(whole+decimal);
  return scale>=0?[digits,10n**BigInt(scale)]:[digits*10n**BigInt(-scale),1n];
};
export function stadiumMembershipTarget(members:number,multiplier:number):number {
  if(!Number.isFinite(members)||members<0||members>1_000_000||!Number.isFinite(multiplier)||multiplier<1||multiplier>20)
    throw new RangeError('Invalid stadium membership or multiplier');
  const [m,md]=fraction(members),[x,xd]=fraction(multiplier),numerator=m*x,denominator=md*xd;
  return Number((2n*numerator+denominator)/(2n*denominator));
}

/** Allocate an already-rounded total once, without creating or losing seats. */
export function allocateStadiumSeats(total:number):Record<typeof stadiumCategories[number],number> {
  if(!Number.isSafeInteger(total)||total<0||total>20_000_000)throw new RangeError('Invalid stadium capacity');
  const parts=stadiumCategories.map((key,index)=>({key,index,seats:Math.floor(total*stadiumRatios[index]/100),remainder:total*stadiumRatios[index]%100}));
  const remaining=total-parts.reduce((sum,part)=>sum+part.seats,0);
  const ranked=[...parts].sort((a,b)=>b.remainder-a.remainder||a.index-b.index);
  for(let index=0;index<remaining;index++)ranked[index].seats++;
  return Object.fromEntries(parts.map(part=>[part.key,part.seats])) as Record<typeof stadiumCategories[number],number>;
}
