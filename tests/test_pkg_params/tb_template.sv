{% extends "lib/tb_base.sv" %}

{% block seq %}
    {% sv_line_anchor %}
    assert(busdecoder_pkg::N_REGS == {{testcase.n_regs}});
    assert(busdecoder_pkg::REGWIDTH == {{testcase.regwidth}});
    assert(busdecoder_pkg::NAME == "{{testcase.name}}");
{% endblock %}
