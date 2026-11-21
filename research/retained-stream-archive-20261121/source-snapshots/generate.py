"""Fixed analytic full-word payloads and guarded code, never measured table data."""
MASK=(1<<64)-1
SEED=0x9e3779b97f4a7c15
LINE_MUL=0xd1b54a32d192ed03
WORD_MUL=0x94d049bb133111eb


def data_words(index):return [(SEED^(((index+1)*LINE_MUL)&MASK)^(((word+1)*WORD_MUL)&MASK)) for word in range(8)]


def code_words(index):
    instructions=[(index<<20)|(10<<7)|0x13]
    for k in range(1,8):
        immediate=((index+1)*(2*k+1)+37*k)&2047
        instructions += [(6<<20)|(10<<15)|(1<<12)|(10<<7)|0x13,
                         (immediate<<20)|(10<<15)|(4<<12)|(10<<7)|0x13]
    instructions.append(0x8067)
    return [instructions[n]|(instructions[n+1]<<32) for n in range(0,16,2)]


def expected_return(index):
    value=index
    for k in range(1,8):value=((value<<6)&MASK)^(((index+1)*(2*k+1)+37*k)&2047)
    return value


def text(max_lines,max_sets):
    if not 1<=max_lines<=2048 or max_sets<1 or max_sets&(max_sets-1) or max_sets>2048:raise ValueError('fixed generator bounds')
    functions=((max_lines+max_sets-1)//max_sets)*max_sets
    if len({expected_return(i) for i in range(functions)})!=functions:raise ValueError('nonunique code results')
    if len({word for i in range(max_lines) for word in data_words(i)})!=8*max_lines:raise ValueError('nonunique data words')
    rows=['.section .text.retained_capacity_targets,"ax",@progbits','.option push','.option norvc',
          '.balign '+str(64*max_sets)+',0','.zero '+str(64*max_sets),'.global retained_capacity_code_base','retained_capacity_code_base:']
    for index in range(functions):
        name='retained_capacity_code_'+str(index)
        rows += ['.global '+name,'.type '+name+',@function',name+':','addi a0,zero,'+str(index)]
        for k in range(1,8):rows+=['slli a0,a0,6','xori a0,a0,'+str(((index+1)*(2*k+1)+37*k)&2047)]
        rows+=['ret','.size '+name+',.-'+name,'.zero 128']
    rows+=['.zero '+str(64*max_sets),'.option pop','.section .data.retained_capacity_targets,"aw",@progbits',
           '.balign '+str(64*max_sets),'.global retained_capacity_data_base','retained_capacity_data_base:']
    for index in range(max_lines):rows+=['.quad '+','.join('0x%016x'%word for word in data_words(index))]
    rows+=['.global retained_capacity_data_end','retained_capacity_data_end:']
    return '\n'.join(rows)+'\n',functions
