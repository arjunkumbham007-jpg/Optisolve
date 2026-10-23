from pathlib import Path

path = Path(__file__).resolve().parents[1] / "visualizer" / "lpp_animation.py"
if not path.exists():
    raise SystemExit(f"Visualizer file not found: {path}")

source = path.read_text(encoding="utf-8")
old = '''        objective_text = MathTex(
            rf"\\max Z = {linear_expression(coefficients, ['x_1', 'x_2'])}",'''
new = '''        sense_symbol = r"\\max" if model.get("sense") == "maximize" else r"\\min"
        objective_text = MathTex(
            rf"{sense_symbol} Z = {linear_expression(coefficients, ['x_1', 'x_2'])}",'''

if new in source:
    print("Visualizer objective label already supports min/max.")
elif old in source:
    path.write_text(source.replace(old, new, 1), encoding="utf-8")
    print("Updated the Manim objective label to reflect max or min.")
else:
    raise SystemExit(
        "Could not find the expected objective_text block; no changes made. "
        "Inspect visualizer/lpp_animation.py and update the label manually."
    )
