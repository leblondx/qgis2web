from qgis.core import QgsExpression, QgsExpressionNode, QgsMessageLog, Qgis
import re
import json

whenfunctions = []

binary_ops = [
    "||", "&&",
    "==", "!=", "<=", ">=", "<", ">", "~",
    "LIKE", "NOT LIKE", "ILIKE", "NOT ILIKE", "===", "!==",
    "+", "-", "*", "/", "//", "%", "^",
    "+"
]

unary_ops = ["!", "-"]


def gen_func_stubs():
    """
    Generate function stubs for QGIS functions.
    """
    funcs = QgsExpression.Functions()
    functions = []
    temp = """function %s(values, context) {
    return false;
};
"""
    for func in funcs:
        name = func.name()
        if name.startswith("$"):
            continue
        newfunc = temp % f"fnc_{name}"
        functions.append(newfunc)
    return "\n".join(functions)


def compile(expstr, name=None, mapLib=None):
    """
    Convert a QgsExpression into a JS function.
    """
    return exp2func(expstr, name, mapLib)


def exp2func(expstr, name=None, mapLib=None):
    """
    Convert a QgsExpression into a JS function.
    """
    global whenfunctions
    whenfunctions = []
    exp = QgsExpression(expstr)
    js = walkExpression(exp.rootNode(), mapLib=mapLib)
    if name is None:
        import random
        import string
        name = 'exp_' + ''.join(random.choice(string.ascii_lowercase) for _ in range(4))
    name = f"exp_{name}_eval_expression"
    temp = """
function %s(context) {
    // %s

    var feature = context.feature;
    %s
    if (feature.properties) {
        return %s;
    } else {
        return %s;
    }
}""" % (name,
        exp.dump(),
        "\n".join(whenfunctions),
        js,
        js.replace("feature.properties['", "feature['"))
    return temp, name, exp.dump()


def walkExpression(node, mapLib):
    if node is None:
        jsExp = "null"
    elif node.nodeType() == QgsExpressionNode.ntBinaryOperator:
        jsExp = handle_binary(node, mapLib)
    elif node.nodeType() == QgsExpressionNode.ntUnaryOperator:
        jsExp = handle_unary(node, mapLib)
    elif node.nodeType() == QgsExpressionNode.ntInOperator:
        jsExp = handle_in(node, mapLib)
    elif node.nodeType() == QgsExpressionNode.ntFunction:
        jsExp = handle_function(node, mapLib)
    elif node.nodeType() == QgsExpressionNode.ntLiteral:
        jsExp = handle_literal(node)
    elif node.nodeType() == QgsExpressionNode.ntColumnRef:
        jsExp = handle_columnRef(node, mapLib)
    elif node.nodeType() == QgsExpressionNode.ntCondition:
        jsExp = handle_condition(node, mapLib)
    return jsExp


def handle_condition(node, mapLib):
    global condtioncounts
    subexps = re.findall(r"WHEN(\s+.*?\s+)THEN(\s+.*?\s+)", node.dump())
    QgsMessageLog.logMessage(subexps, "qgis2web", level=Qgis.Info)
    js = ""
    for count, sub in enumerate(subexps, start=1):
        when = sub[0].strip()
        then = sub[1].strip()
        QgsMessageLog.logMessage(then, "qgis2web", level=Qgis.Info)
        whenpart = QgsExpression(when)
        thenpart = QgsExpression(then)
        whenjs = walkExpression(whenpart.rootNode(), mapLib)
        thenjs = walkExpression(thenpart.rootNode(), mapLib)
        style = "if" if count == 1 else "else if"
        js += """
        %s %s {
          return %s;
        }
        """ % (style, whenjs, thenjs)
        js = js.strip()
    elsejs = "null"
    if "ELSE" in node.dump():
        elseexps = re.findall(r"ELSE(\s+.*?\s+)END", node.dump())
        elsestr = elseexps[0].strip()
        exp = QgsExpression(elsestr)
        elsejs = walkExpression(exp.rootNode(), mapLib)
    funcname = "_CASE()"
    temp = """function %s {
    %s
    else {
     return %s;
    }
    };""" % (funcname, js, elsejs)
    whenfunctions.append(temp)
    return funcname


def handle_binary(node, mapLib):
    op = node.op()
    retOp = binary_ops[op]
    left = node.opLeft()
    right = node.opRight()
    retLeft = walkExpression(left, mapLib)
    retRight = walkExpression(right, mapLib)
    if retOp == "//":
        return f"(Math.floor({retLeft} {retOp} {retRight}))"
    elif retOp == "ILIKE":
        return f'({retLeft[:-1]}.toLowerCase().indexOf({re.sub("[_%]", "", retRight)}.toLowerCase()) > -1)'
    elif retOp == "LIKE":
        return f'({retLeft[:-1]}.indexOf({re.sub("[_%]", "", retRight)}) > -1)'
    elif retOp == "NOT ILIKE":
        return f'({retLeft[:-1]}.toLowerCase().indexOf({re.sub("[_%]", "", retRight)}.toLowerCase()) == -1)'
    elif retOp == "NOT LIKE":
        return f'({retLeft[:-1]}.indexOf({re.sub("[_%]", "", retRight)}) == -1)'
    elif retOp == "~":
        return f"/{retRight[1:-2]}/.test({retLeft[:-1]})"
    else:
        return f"({retLeft} {retOp} {retRight})"


def handle_unary(node, mapLib):
    op = node.op()
    operand = node.operand()
    retOp = unary_ops[op]
    retOperand = walkExpression(operand, mapLib)
    return f"{retOp} {retOperand} "


def handle_in(node, mapLib):
    operand = node.node()
    retOperand = walkExpression(operand, mapLib)
    list = node.list().dump()
    retList = json.dumps(list)
    notIn = "!" if node.isNotIn() else ""
    return f"{notIn}{retList}.indexOf({retOperand}) > -1 "


def handle_literal(node):
    val = node.value()
    quote = ""
    if val is None:
        val = "null"
    elif isinstance(val, str):
        quote = "'"
        val = val.replace("\n", "\\n")
    return f"{quote}{str(val)}{quote}"


def handle_function(node, mapLib):
    fnIndex = node.fnIndex()
    func = QgsExpression.Functions()[fnIndex]
    args = node.args().list()
    retFunc = (func.name())
    retArgs = [walkExpression(arg, mapLib) for arg in args]
    retArgs = ",".join(retArgs)
    return f"fnc_{retFunc}([{retArgs}], context)"


def handle_columnRef(node, mapLib):
    if mapLib is None:
        return f"feature['{node.name()}'] "
    if mapLib == "Leaflet":
        return f"feature.properties['{node.name()}'] "
    else:
        return f"feature.get('{node.name()}') "


def render_examples():
    lines = [
        """var feature = {
            COLA: 1,
            COLB: 2,
            WAT: 'Hello World'
        };""",
        """var context = {
            feature: feature,
            variables: {}
        };"""
    ]

    def render_call(name):
        callstr = "var result = {0}(context);".format(name)
        callstr += "\nconsole.log(result);"
        return callstr

    def render_example(exp):
        data, name, dump = exp2func(exp, mapLib="Leaflet")
        lines.append(data)
        lines.append(render_call(name))

    import os
    if not os.path.exists("examples"):
        os.mkdir("examples")

    with open(r"examples\qgsfunctions.js", "w") as f:
        # Write out the functions first.
        funcs = gen_func_stubs()
        f.write(funcs)

    with open(r"examples\qgsexpression.js", "w") as f:
        exp = "(1 + 1) * 3 + 5"
        render_example(exp)
        exp = "NOT @myvar = format('some string %1 %2', 'Hello', 'World')"
        render_example(exp)
        exp = """
        CASE
            WHEN to_int(123.52) = @myvar THEN to_real(123)
            WHEN (1 + 2) = 3 THEN 2
            ELSE to_int(1)
        END
            OR (2 * 2) + 5 = 4"""
        render_example(exp)
        exp = """
        CASE
            WHEN "COLA" = 1 THEN 1
            WHEN (1 + 2) = 3 THEN 2
            ELSE 3
        END
        """
        render_example(exp)
        f.writelines("\n\n".join(lines))


def compile_to_file(exp, name=None, mapLib=None, filename="expressions.js"):
    """
    Generate JS function to file from exp and append it to the end of the given file name.
    :param exp: The expression to export to JS
    :return: The name of the function you can call.
    """
    functionjs, name, _ = compile(exp, name=name, mapLib=mapLib)
    with open(filename, "a") as f:
        f.write("\n\n")
        f.write(functionjs)

    return name


if __name__ == "__main__":
    render_examples()
