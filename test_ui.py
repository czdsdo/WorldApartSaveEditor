"""Internal widget integration test; no writes to live save data."""
import time
from unittest.mock import patch
from editor import Editor

app=Editor()
app.withdraw()
def fail(*args,**kwargs):raise AssertionError(str(args))
with patch('editor.messagebox.showerror',side_effect=fail):
    deadline=time.monotonic()+20
    while app.session is None or app.busy:
        app.update()
        if time.monotonic()>deadline:raise AssertionError('UI load timed out')
        time.sleep(.02)
    assert len(app.slots)==5
    assert len(app.bag.get_children())>0
    group=app.quick.get_children()[0]
    iid=app.quick.get_children(group)[1]
    app.quick.selection_set(iid);app.select_node(app.quick)
    node=app.selected;old=node.value
    app.value_text.delete('1.0','end');app.value_text.insert('1.0',str(old+17))
    app.apply_value()
    assert app.session.world.value(node)==old+17
    assert len(app.change_tree.get_children())==1
    assert str(app.save_btn['state'])=='normal'
    app.query.set('cultivate_exp');app.search()
    assert len(app.all.get_children())>0
    change_iid=app.change_tree.get_children()[0]
    app.change_tree.selection_set(change_iid);app.undo_selected()
    assert not app.session.world.changes
    assert str(app.save_btn['state'])=='disabled'
    print('PASS: five slots loaded; quick edit, inventory, search, change preview and undo integrated.')
app.destroy()
