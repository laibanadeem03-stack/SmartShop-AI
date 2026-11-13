import { describe,expect,it } from 'vitest';
import { FEATURED_CATEGORIES,filterParams,parseFilters } from './catalogFilters.js';
describe('catalog URL contract',()=>{
  it('roundtrips verified filters and model-number search terms',()=>{
    const value={q:'ZX-42 USB-C',category:FEATURED_CATEGORIES[0],page:2};
    expect(parseFilters('?'+filterParams(value))).toMatchObject(value);
  });
  it('normalizes featured category case and whitespace',()=>{
    expect(parseFilters('?category=screen%20%20protectors').category).toBe('Screen Protectors');
  });
  it('handles invalid and oversized pages without sending backend-invalid values',()=>{
    for(const p of ['0','-1','1.5','1000001','NaN','999999999999999999999'])expect(parseFilters('?page='+p).page).toBe(1);
    expect(parseFilters('?page=527').page).toBe(527);
  });
  it('flags unknown featured categories and bounds search length',()=>{
    expect(parseFilters('?category=Invented').unknownCategory).toBe(true);
    expect(parseFilters('?q='+'x'.repeat(250)).q).toHaveLength(200);
  });
});
