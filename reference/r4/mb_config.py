"""HQ-scoped MB override and fail-closed runtime evidence."""
import re


def build_mb_options(text,events,seedj,seedi):
    text,n=re.subn(r'(?m)^\s*set\s+nfull\s+\d+[^\n]*$', 'set nfull '+str(events),text)
    assert n==1,'ambiguous nfull in production template'
    text=re.sub(r'(?m)^\s*set\s+seed[ji]\s+[^\n]*$', '',text)
    # iskip belongs to hqoptns, NOT the generic EPOS set parser. Preserve the
    # shared hq.i and all physics; override only this selection switch in HQ scope.
    text+='\n! Independent complete MB reference; HQ-scoped override.\nbeginoptns hq\nset iskip 0\nendoptns hq\nset seedj %d\nset seedi %d\n'%(seedj,seedi)
    return text


def checked_mb_stdout(text):
    values=[int(x) for x in re.findall(r'(?m)^\s*iskip\s*:\s*(-?\d+)\s*$',text)]
    assert values and set(values)=={0},'HQ runtime iskip is not unambiguously zero'
    assert not re.search(r'No c quarks, event skipped',text),'MB skipped no-charm events'
    assert re.search(r'(?m)^stop program;',text),'missing normal generator completion'
    return dict(runtime_iskip=values,skipped_no_charm=0,normal_stop=True)
