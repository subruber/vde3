import sys
import os
import simplejson
import re

# XXX:
# - possible alternatives to declare auto-generated code:
#   + a file compliant with http://json-schema.org/
#   + doxygen tags instead of a json struct

# Schema for input json struct:

# {
#   "basename": "struct_and_files_prefix",
#   "wrappables": [
#     {
#       "name": "the.command.name",
#       "fun": "function_name",
#       "description": "Function help",
#       "parameters":
#         [
#           {
#             "name": "param1"
#             "description": "Parameter description"
#             "type": "int/bool/string"
#           },
#
#           ...,
#
#           {
#             "name": "paramN"
#             "description": "Parameter description"
#             "type": "int/bool/string"
#           }
#         ]
#     }
#     ...
#   ]
# }

COMMANDS_SUFFIX='_commands.h'
WRAPPERS_SUFFIX='_commands.c'

typemap = {'int': ('int', 'vde_sobj_type_int', 'vde_sobj_get_int'),
           'double': ('double', 'vde_sobj_type_double', 'vde_sobj_get_double'),
           'bool': ('bool', 'vde_sobj_type_boolean', 'vde_sobj_get_boolean'),
           'string': ('char *', 'vde_sobj_type_string', 'vde_sobj_get_string'),
}

def usage():
  print 'Usage: %s <filename>' % sys.argv[0]

# XXX: escape descriptions?

def gen_command(info):
  return ['{ "%(name)s", %(fun)s_wrapper, '
          '  "%(description)s", %(fun)s_wrapper_params },' % info]

def gen_wrapper_declaration(info):
  return ['int %s_wrapper(%s, %s, %s);' % (info['fun'],
                                           'vde_component *component',
                                           'vde_sobj *in', 'vde_sobj **out')]

def gen_params(info):
  res = []
  res.append('static vde_argument %(fun)s_wrapper_params[] = {' % info)

  for p in info['parameters']:
    res.append('  {"%(name)s", "%(description)s", "%(type)s"},' % p)

  res.append('  { NULL, NULL, NULL },')
  res.append('};')
  return res

def gen_wrapper(info):
  params = ''
  num_params = len(info['parameters'])
  # function signature
  args = ['vde_component *component']
  args.extend(["%(type)s %(name)s" % p for p in info['parameters']])
  args.append('vde_sobj **out')
  wrap = ['int %s(%s);' % (info['fun'], ', '.join(args))]
  wrap.append('')
  wrap.append('int %s_wrapper(%s, %s, %s) {' % (info['fun'],
                                                'vde_component *component',
                                                'vde_sobj *in',
                                                'vde_sobj **out'))

  # declare variables
  for p in info['parameters']:
    var = p['name']
    json_var = 'json_%s' % var
    type = p['type']
    wrap.append('  %s %s; vde_sobj *%s;' % (typemap[type][0], var, json_var))
  # sanity check on received json
  wrap.append('  if (!vde_sobj_is_type(in, vde_sobj_type_array)) {')
  wrap.append('    *out = vde_sobj_new_string("Did not receive an array");')
  wrap.append('    return -1;')
  wrap.append('  }')
  wrap.append('  if (vde_sobj_array_length(in) != %s) {' % num_params)
  wrap.append('    *out = vde_sobj_new_string("Expected %s params");' %
              num_params)
  wrap.append('    return -1;')
  wrap.append('  }')
  # check and convert parameters
  for i, p in enumerate(info['parameters']):
    var = p['name']
    json_var = 'json_%s' % var
    type = p['type']
    wrap.append('  %s = vde_sobj_array_get_idx(in, %s);' % (json_var, i))
    wrap.append('  if (!vde_sobj_is_type(%s, %s)) {' %
                (json_var, typemap[type][1]))
    wrap.append('    *out = vde_sobj_new_string("Param %s not a %s");' %
                (var, type))
    wrap.append('    return -1;')
    wrap.append('  }')
    wrap.append('  %s = %s(%s);' % (var, typemap[type][2], json_var))
    params += '%s, ' % var
  # call function
  wrap.append('  return %s(component, %sout);' % (info['fun'], params))
  wrap.append('}')
  return wrap

# this function returns a tuple of lists, each containing a line
def do_wrap(wrappable):
  declarations = []
  params = []
  commands = []
  wrappers = []

  for info in wrappable:
    # TODO: check info is a dict, parameters is an array, type is in typemap
    declarations.extend(gen_wrapper_declaration(info))
    params.extend(gen_params(info))
    commands.extend(gen_command(info))
    wrappers.extend(gen_wrapper(info))
    wrappers.append('')  # separate wrappers with and empty line

  return declarations, params, commands, wrappers


if not len(sys.argv) == 2:
  usage()
  sys.exit(-1)

wrappable_file = sys.argv[1]

data = simplejson.load(open(wrappable_file, 'r')) # TODO: catch exceptions

basename = data['basename']
headername = '%s%s' % (basename, COMMANDS_SUFFIX)
header_guard = '__%s__' % re.sub('[^_A-Z]', '_', headername.upper())

declarations, params, commands, wrappers = do_wrap(data['wrappables'])

cmd_out = open(headername, 'w') # TODO: catch
cmd_out.write('/* Autogenerated file, do not edit!! */\n')
cmd_out.write('\n')
cmd_out.write('#ifndef %s\n' % header_guard)
cmd_out.write('#define %s\n' % header_guard)
cmd_out.write('\n')
cmd_out.write('#include <stdbool.h>\n')
cmd_out.write('#include <vde3.h>\n')
cmd_out.write('#include <vde3/common.h>\n')
cmd_out.write('#include <vde3/command.h>\n')
cmd_out.write('\n')
for el in declarations:
  cmd_out.write(el + '\n')
cmd_out.write('\n')
for el in params:
  cmd_out.write(el + '\n')
cmd_out.write('\n')

cmd_out.write('static vde_command %s_commands [] = {\n' % basename)
commands.append('{ NULL, NULL, NULL, NULL },')
for c in commands:
  cmd_out.write('  %s\n' % c)
cmd_out.write('};\n')
cmd_out.write('\n')
cmd_out.write('#endif /* %s */\n' % header_guard)
cmd_out.write('\n')

cmd_out.close()

wrap_out = open('%s%s' % (basename, WRAPPERS_SUFFIX), 'w') # TODO: catch
wrap_out.write('/* Autogenerated file, do not edit!! */\n')
wrap_out.write('\n')
wrap_out.write('#include "%s"\n' % headername)
wrap_out.write('\n')
for w in wrappers:
  wrap_out.write(w + '\n')
wrap_out.close()

