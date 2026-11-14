import os
import sys
import json
import threading
import traceback
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from save_core import DEFAULT_ROOT, SaveSession, Document, decrypt

APP_DIR = Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
BACKUPS = APP_DIR / 'backups'
ATTRS = {1:'当前气血',2:'攻击',3:'防御',4:'气血上限',5:'机缘',6:'魅力',7:'移动速度',8:'寿元',11:'气血加成',12:'攻击加成',13:'防御加成',21:'速度',22:'灵力上限',23:'当前韧性',24:'韧性上限',25:'当前灵力',26:'共鸣',27:'共鸣上限',28:'护盾',51:'金伤害加成',52:'木伤害加成',53:'水伤害加成',54:'火伤害加成',55:'土伤害加成',101:'伤害加成',102:'伤害减免',103:'吸血效率',104:'治疗效率',108:'破韧效率',111:'暴击率',112:'暴击伤害',113:'暴击抵抗',114:'暴伤减免',115:'命中率',116:'闪避率',117:'无视防御',118:'无视防御抵抗',119:'追击概率',120:'反击概率',121:'反击增伤',122:'反击抗性',200:'当前体力',201:'体力上限'}
LABELS = {'playerName':'角色名称','combat':'战斗与修炼','base_attrs':'基础属性','growth_attrs':'成长属性','permanent_attrs':'永久属性来源','cultivate_layer_id':'修炼层级 ID','cultivate_exp':'当前修为','cultivate_reserve_exp':'储备修为','alchemy':'炼器','alchemy_level':'炼器等级','alchemy_exp':'炼器经验','alchemy_talent_points':'炼器天赋点','refining_pills':'炼丹','rp_level':'炼丹等级','rp_exp':'炼丹经验','talent_path':'天赋与灵根','talent_path_points':'天赋路径点数','spirit_point_remain':'剩余灵根点','spirit_root_point_map':'灵根点分配','sect_contribution_total':'累计宗门贡献','current_soul_count':'魂幡魂魄数量','current_demonic_qi':'当前魔气','behavior_value':'行为与声望','player_good':'善行值','player_evil':'恶行值','interact_attributes':'交互属性','bag':'背包','items':'物品列表','count':'数量','item_id':'物品 ID','uid':'唯一编号','is_equipped':'已装备','is_new':'新获得','learned_skills':'已学技能','learned_support_skills':'已学辅助技能','npc_relation':'人物关系','player_prop_evil':'邪性值','entityId':'实体 ID','currentGameTime':'游戏时间','npcs':'NPC 数据','spaces':'场景数据','playerModel':'玩家数据'}
KINDS = {'int':'整数','float':'小数','str':'文本','bool':'布尔','map':'字典','array':'列表','null':'空值（只读）','binary':'二进制（只读）','extension':'扩展数据（只读）'}

def fmt(value):
    if isinstance(value,bool): return 'true' if value else 'false'
    if isinstance(value,float): return format(value,'.9g')
    if value is None: return 'null'
    if isinstance(value,bytes): return '二进制 · '+str(len(value))+' 字节'
    return str(value)

def path_text(path): return ' / '.join(str(k) for k in path)
def label(node):
    k = node.path[-1] if node.path else 'root'
    if len(node.path)>1 and node.path[-2] in ('base_attrs','growth_attrs','permanent_attrs'):
        return ATTRS.get(k,'属性')+'  ['+str(k)+']'
    return LABELS.get(k,str(k))

class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('不问凡尘 · 存档修改器')
        self.geometry('1220x820')
        self.minsize(1000,680)
        self.state('zoomed')
        self.configure(bg='#eef2f5')
        self.session = None
        self.slots = []
        self.rows = {}
        self.selected = None
        self.busy = False
        self.counter = 0
        self.slot_index = -1
        self.edit_dirty = False
        self.root_path = tk.StringVar(value=str(DEFAULT_ROOT))
        self.status = tk.StringVar(value='选择存档，读取后双击字段即可修改。')
        style = ttk.Style(self); style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background='#eef2f5',foreground='#223548')
        style.configure('Treeview',background='white',fieldbackground='white',rowheight=29,font=('Microsoft YaHei UI',10))
        style.configure('Treeview.Heading',font=('Microsoft YaHei UI',10,'bold'),background='#e5ebf1',padding=7)
        style.map('Treeview',background=[('selected','#d7e9f4')],foreground=[('selected','#133a54')])
        style.configure('TButton',padding=(12,7))
        style.configure('Accent.TButton',background='#25627a',foreground='white',font=('Microsoft YaHei UI',10,'bold'))
        style.map('Accent.TButton',background=[('active','#357d95')])
        style.configure('TNotebook.Tab',padding=(17,10))
        style.configure('Hint.TLabel',foreground='#667788')
        head = tk.Frame(self,bg='#193747',height=85); head.pack(fill='x')
        tk.Label(head,text='不问凡尘',font=('Microsoft YaHei UI',24,'bold'),bg='#193747',fg='#f6e6bd').pack(side='left',padx=24,pady=17)
        tk.Label(head,text='存档修改器  /  本地离线编辑',font=('Microsoft YaHei UI',12),bg='#193747',fg='#d0dce3').pack(side='left')
        tk.Label(head,text='自动备份 · 完整性校验',font=('Microsoft YaHei UI',10),bg='#193747',fg='#adcbd7').pack(side='right',padx=24)
        bar = ttk.Frame(self,padding=(18,12)); bar.pack(fill='x')
        ttk.Entry(bar,textvariable=self.root_path).pack(side='left',fill='x',expand=True)
        ttk.Button(bar,text='选择目录',command=self.browse).pack(side='left',padx=6)
        ttk.Button(bar,text='刷新存档',command=self.scan).pack(side='left')
        slotbar = ttk.Frame(self,padding=(18,0,18,12)); slotbar.pack(fill='x')
        ttk.Label(slotbar,text='存档槽').pack(side='left',padx=(0,12))
        self.slot_combo = ttk.Combobox(slotbar,state='readonly',width=64); self.slot_combo.pack(side='left',fill='x',expand=True)
        self.slot_combo.bind('<<ComboboxSelected>>',lambda e:self.load_selected())
        ttk.Button(slotbar,text='重新读取',command=self.load_selected).pack(side='left',padx=(8,0))
        self.info = ttk.Label(self,text='正在发现存档…',padding=(20,0,20,12),style='Hint.TLabel'); self.info.pack(fill='x')
        body = ttk.Panedwindow(self,orient='horizontal'); body.pack(fill='both',expand=True,padx=18)
        left = ttk.Frame(body); body.add(left,weight=4)
        self.tabs = ttk.Notebook(left); self.tabs.pack(fill='both',expand=True)
        self.quick_frame = ttk.Frame(self.tabs); self.tabs.add(self.quick_frame,text='角色与修炼')
        ttk.Label(self.quick_frame,text='选择字段修改。层级、技能和任务等关联数据可在「全部数据」查看。',style='Hint.TLabel',padding=10).pack(fill='x')
        self.quick = self.make_tree(self.quick_frame,('value','type'),('当前 / 待保存值','类型'))
        self.bag_frame = ttk.Frame(self.tabs); self.tabs.add(self.bag_frame,text='背包物品')
        ttk.Label(self.bag_frame,text='修改已有物品的数量；名称未确认的物品按真实 ID 显示，不创建未知物品。',style='Hint.TLabel',padding=10).pack(fill='x')
        self.bag = self.make_tree(self.bag_frame,('value','type'),('数量','物品类型 / 装备状态'))
        self.all_frame = ttk.Frame(self.tabs); self.tabs.add(self.all_frame,text='全部数据')
        searchbar = ttk.Frame(self.all_frame,padding=8); searchbar.pack(fill='x')
        self.query = tk.StringVar()
        ent=ttk.Entry(searchbar,textvariable=self.query); ent.pack(side='left',fill='x',expand=True); ent.bind('<Return>',lambda e:self.search())
        ttk.Button(searchbar,text='搜索字段 / 值',command=self.search).pack(side='left',padx=5)
        ttk.Button(searchbar,text='树形浏览',command=self.populate_all).pack(side='left')
        self.all = self.make_tree(self.all_frame,('value','type'),('当前 / 待保存值','类型'))
        self.all.bind('<<TreeviewOpen>>',self.expand)
        self.change_frame=ttk.Frame(self.tabs);self.tabs.add(self.change_frame,text='待保存 (0)')
        self.change_tree=self.make_tree(self.change_frame,('before','after'),('原值','新值'))
        ttk.Button(self.change_frame,text='撤销选中修改',command=self.undo_selected).pack(anchor='e',pady=8)
        self.backup_frame=ttk.Frame(self.tabs);self.tabs.add(self.backup_frame,text='备份与恢复')
        self.backup_tree=self.make_tree(self.backup_frame,('time','reason'),('备份时间','原因'))
        actions=ttk.Frame(self.backup_frame,padding=8);actions.pack(fill='x')
        ttk.Button(actions,text='刷新备份',command=self.refresh_backups).pack(side='left')
        ttk.Button(actions,text='打开备份目录',command=self.open_backups).pack(side='left',padx=6)
        ttk.Button(actions,text='恢复选中备份',command=self.restore).pack(side='right')
        right=ttk.Frame(body,padding=(18,12),width=290);body.add(right,weight=1)
        ttk.Label(right,text='编辑字段',font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w',pady=(0,14))
        self.field_label=ttk.Label(right,text='从左侧选择一个字段',wraplength=265);self.field_label.pack(fill='x')
        self.field_path=ttk.Label(right,text='',wraplength=265,style='Hint.TLabel');self.field_path.pack(fill='x',pady=12)
        self.original_label=ttk.Label(right,text='',wraplength=265);self.original_label.pack(fill='x',pady=8)
        self.value_text=tk.Text(right,height=5,width=25,font=('Microsoft YaHei UI',11),wrap='word',relief='solid',bd=1)
        self.value_text.pack(fill='x',pady=10)
        self.value_text.bind('<<Modified>>',self.text_modified)
        self.apply_btn=ttk.Button(right,text='应用到待保存列表',style='Accent.TButton',command=self.apply_value,state='disabled');self.apply_btn.pack(fill='x')
        ttk.Label(right,text='应用后仍需点击下方「备份并保存」。\n\n百分比字段保留游戏原始比例，例如 0.1 表示 10%。基础数值还会叠加装备、功法等效果。\n\n高级字段可能存在关联约束。建议先小幅修改，并从对应存档槽读档。',wraplength=265,style='Hint.TLabel',justify='left').pack(fill='x',pady=20)
        foot=ttk.Frame(self,padding=18)
        foot.pack(before=body, side='bottom', fill='x')
        self.save_btn=ttk.Button(foot,text='备份并保存 (0)',style='Accent.TButton',command=self.save,state='disabled');self.save_btn.pack(side='right')
        ttk.Button(foot,text='撤销全部修改',command=self.undo_all).pack(side='right',padx=10)
        ttk.Label(foot,textvariable=self.status,wraplength=650,style='Hint.TLabel').pack(side='left',fill='x',expand=True)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self.scan)

    def make_tree(self,parent,columns,headings):
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=columns,show='tree headings',selectmode='browse')
        tree.heading('#0',text='字段 / 项目');tree.column('#0',width=350,minwidth=160)
        for c,h in zip(columns,headings):tree.heading(c,text=h);tree.column(c,width=145,minwidth=85)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        tree.tag_configure('changed',foreground='#a45b00')
        tree.bind('<<TreeviewSelect>>',lambda e:self.select_node(tree))
        tree.bind('<Double-1>',lambda e:self.value_text.focus_set())
        return tree

    def text_modified(self,event=None):
        if self.value_text.edit_modified():self.edit_dirty=True;self.value_text.edit_modified(False)

    def confirm_discard(self):
        if self.busy:return False
        if self.edit_dirty or (self.session and self.session.world.changes):
            return messagebox.askyesno('尚有未保存修改','继续将丢弃尚未保存的修改，是否继续？',parent=self)
        return True

    def browse(self):
        if not self.confirm_discard():return
        p=filedialog.askdirectory(initialdir=self.root_path.get(),title='选择 StorageV1 或具体存档槽目录')
        if p:self.root_path.set(p);self.scan(discard_checked=True)

    def scan(self,discard_checked=False):
        if self.busy:return
        if not discard_checked and not self.confirm_discard():return
        root=Path(self.root_path.get())
        if not root.is_dir():messagebox.showerror('目录不存在','请选择有效存档目录。');return
        try:
            paths=sorted(root.rglob('gameworld.msgpack'),key=lambda p:p.stat().st_mtime,reverse=True)
            paths=[p for p in paths if (p.parent/'meta.msgpack').exists() and not (p.parent/'backup.json').exists()]
            slots=[];values=[]
            for p in paths:
                try:
                    d=Document(decrypt((p.parent/'meta.msgpack').read_bytes())).root
                    def v(k):return d.at(k).value
                    title=f'{p.parent.name}  |  {v("characterName")}  |  {v("cultivationLevelText")}  |  {v("gameTimeText")}'
                except Exception as e:title=f'{p.parent.name}  |  无法读取：{e}'
                slots.append(p.parent);values.append(title+'  ·  '+p.parent.parent.parent.name[:8])
            self.session=None;self.selected=None;self.edit_dirty=False
            self.rows.clear()
            for tree in (self.quick,self.bag,self.all,self.change_tree,self.backup_tree):tree.delete(*tree.get_children())
            self.clear_edit();self.save_btn.configure(state='disabled')
            self.slots=slots;self.slot_combo['values']=values;self.slot_index=-1
            if slots:self.slot_combo.current(0);self.load_selected(discard_checked=True)
            else:self.slot_combo.set('');self.info.configure(text='此目录未找到可编辑的存档。');self.status.set('需要成对的 gameworld.msgpack 和 meta.msgpack。')
        except Exception as e:self.error(e)

    def load_selected(self,discard_checked=False):
        i=self.slot_combo.current()
        if self.busy or i<0:return
        if not discard_checked and not self.confirm_discard():
            if self.slot_index>=0:self.slot_combo.current(self.slot_index)
            return
        self.busy=True;self.save_btn.configure(state='disabled');self.slot_combo.configure(state='disabled')
        self.apply_btn.configure(state='disabled');self.status.set('正在校验并读取存档…')
        self.load_result=None
        def worker():
            try:self.load_result=(SaveSession(self.slots[i]),None)
            except Exception as e:self.load_result=(None,e)
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            if self.load_result is None:self.after(80,poll);return
            session,error=self.load_result;self.busy=False;self.slot_combo.configure(state='readonly')
            if error:
                self.session=None;self.error(error);return
            self.session=session;self.slot_index=i;self.rows.clear();self.edit_dirty=False;self.clear_edit()
            m=session.meta.root
            self.info.configure(text=f'已验证 A1SV  •  {m.at("characterName").value}  •  {m.at("cultivationLevelText").value}  •  {m.at("gameTimeText").value}  •  {session.slot.name}')
            self.populate_quick();self.populate_bag();self.populate_all();self.refresh_changes();self.refresh_backups()
            self.status.set('读取成功。支持游戏运行时保存；保存后请重新加载对应存档。')
        self.after(80,poll)

    def clear_edit(self):
        self.selected=None;self.field_label.configure(text='从左侧选择一个字段');self.field_path.configure(text='');self.original_label.configure(text='')
        self.value_text.delete('1.0','end');self.value_text.edit_modified(False);self.edit_dirty=False;self.apply_btn.configure(state='disabled')

    def insert(self,tree,parent,node,text=None,lazy=False,values=None):
        self.counter+=1;iid='n'+str(self.counter);self.rows[(str(tree),iid)]=node
        doc=self.session.world
        v=f'{len(node.children)} 项' if node.kind in ('map','array') else fmt(doc.value(node))[:160]
        tree.insert(parent,'end',iid=iid,text=text or label(node),values=values or (v,KINDS[node.kind]),tags=('changed',) if node.path in doc.changes else ())
        if lazy and node.children:tree.insert(iid,'end',text='…')
        return iid

    def populate_quick(self):
        self.quick.delete(*self.quick.get_children())
        if not self.session:return
        root=self.session.world.root
        groups=[('角色与修为',[('playerName',),('combat','cultivate_exp'),('combat','cultivate_reserve_exp'),('sect_contribution_total',)]),('天赋与灵根',[('talent_path','talent_path_points'),('talent_path','spirit_point_remain')]),('炼器与炼丹',[('alchemy','alchemy_level'),('alchemy','alchemy_exp'),('alchemy','alchemy_talent_points'),('refining_pills','rp_level'),('refining_pills','rp_exp')]),('其他资源',[('soul_banner','current_soul_count'),('demonic_cultivator','current_demonic_qi')])]
        for title,paths in groups:
            g=self.quick.insert('','end',text=title,open=True)
            for p in paths:
                try:self.insert(self.quick,g,root.at('playerModel',*p))
                except KeyError:pass
        for name,key in [('基础属性','base_attrs'),('成长属性','growth_attrs')]:
            g=self.quick.insert('','end',text=name,open=key=='base_attrs')
            try:
                for _,n in root.at('playerModel','combat',key).children:self.insert(self.quick,g,n)
            except KeyError:pass

    def populate_bag(self):
        self.bag.delete(*self.bag.get_children())
        if not self.session:return
        try:
            for index,item in self.session.world.root.at('playerModel','bag','items').children:
                if item.kind=='null':continue
                try:
                    payload=item.child(1);n=payload.child('count');itemid=payload.child('item_id').value
                    eq=payload.child('is_equipped').value;uid=payload.child('uid').value
                    self.insert(self.bag,'',n,text=f'物品 {itemid}  ·  UID {uid}',values=(fmt(self.session.world.value(n)),f'类型 {item.child(0).value}'+(' / 已装备' if eq else '')))
                except KeyError:continue
        except KeyError:pass

    def populate_all(self):
        self.all.delete(*self.all.get_children())
        if self.session:
            for _,n in self.session.world.root.children:self.insert(self.all,'',n,lazy=True)

    def expand(self,event):
        iid=self.all.focus();n=self.rows.get((str(self.all),iid))
        if not n:return
        children=self.all.get_children(iid)
        if len(children)==1 and (str(self.all),children[0]) not in self.rows:
            self.all.delete(children[0])
            for _,child in n.children:self.insert(self.all,iid,child,lazy=True)

    def search(self):
        if not self.session:return
        q=self.query.get().strip().lower()
        if not q:self.populate_all();return
        self.all.delete(*self.all.get_children());count=0
        for n in self.session.world.nodes.values():
            if n.kind in ('map','array'):continue
            if q in (path_text(n.path)+' '+label(n)+' '+fmt(self.session.world.value(n))).lower():
                self.insert(self.all,'',n,text=path_text(n.path));count+=1
                if count>=500:break
        self.status.set(f'找到 {count} 项'+('（最多展示 500 项，请缩小关键词）' if count==500 else ''))

    def select_node(self,tree):
        if self.busy or not self.session:return
        sel=tree.selection()
        if not sel:return
        n=self.rows.get((str(tree),sel[0]))
        if not n:return
        if self.edit_dirty and self.selected is not None:
            if not messagebox.askyesno('尚未应用','输入框的修改尚未应用，是否丢弃并切换字段？'):return
        self.selected=n
        self.field_label.configure(text=label(n)+' · '+KINDS[n.kind]);self.field_path.configure(text=path_text(n.path))
        self.original_label.configure(text='原值：'+fmt(n.value)[:180])
        self.value_text.delete('1.0','end')
        value=self.session.world.value(n)
        self.value_text.insert('1.0',repr(value) if isinstance(value,float) else fmt(value))
        self.value_text.edit_modified(False);self.edit_dirty=False
        self.apply_btn.configure(state='normal' if n.kind in ('int','float','str','bool') else 'disabled')

    def apply_value(self):
        if not self.session or self.selected is None or self.busy:return
        try:
            n=self.selected;text=self.value_text.get('1.0','end-1c')
            if n.path[-1]=='count' and 'bag' in n.path and not 1 <= int(text.strip()) <= 999999999:
                raise ValueError('背包数量请填写 1 到 999999999。此工具不通过置零删除物品。')
            self.session.world.stage(n,text);self.edit_dirty=False;self.refresh_views()
            self.status.set('已加入待保存列表；原存档尚未改变。')
        except Exception as e:self.error(e)

    def refresh_views(self):
        self.populate_quick();self.populate_bag()
        for iid in list(self.all.get_children()):self.update_row_recursive(self.all,iid)
        self.refresh_changes()

    def update_row_recursive(self,tree,iid):
        n=self.rows.get((str(tree),iid))
        if n:
            v=f'{len(n.children)} 项' if n.kind in ('map','array') else fmt(self.session.world.value(n))[:160]
            tree.item(iid,values=(v,KINDS[n.kind]),tags=('changed',) if n.path in self.session.world.changes else ())
        for c in tree.get_children(iid):self.update_row_recursive(tree,c)

    def refresh_changes(self):
        self.change_tree.delete(*self.change_tree.get_children())
        if not self.session:return
        d=self.session.world
        for p,(v,_) in d.changes.items():self.insert(self.change_tree,'',d.nodes[p],text=path_text(p),values=(fmt(d.nodes[p].value),fmt(v)))
        count=len(d.changes);self.tabs.tab(self.change_frame,text=f'待保存 ({count})')
        self.save_btn.configure(text=f'备份并保存 ({count})',state='normal' if count and not self.busy else 'disabled')

    def undo_selected(self):
        if not self.session or self.busy:return
        sel=self.change_tree.selection()
        if sel:
            n=self.rows.get((str(self.change_tree),sel[0]))
            if n:self.session.world.changes.pop(n.path,None);self.clear_edit();self.refresh_views()

    def undo_all(self):
        if not self.session or self.busy:return
        if messagebox.askyesno('撤销修改','撤销全部尚未保存的修改？'):
            self.session.world.changes.clear();self.clear_edit();self.refresh_views()

    def save(self):
        if not self.session or not self.session.world.changes or self.busy:return
        if self.edit_dirty:
            messagebox.showinfo('请先应用输入','输入框有尚未应用的修改，请先点击「应用到待保存列表」。');return
        changes=self.session.world.changes
        preview='\n'.join(f'{label(self.session.world.nodes[p])}: {fmt(self.session.world.nodes[p].value)} → {fmt(v)}' for p,(v,_) in list(changes.items())[:10])
        if not messagebox.askyesno('确认保存',f'存档槽：{self.session.slot.name}\n共 {len(changes)} 项修改：\n\n{preview}\n\n将先备份完整存档槽，再写入修改。游戏运行时可能覆盖修改，保存后请重新加载对应存档。'):return
        try:
            backup=self.session.save(BACKUPS)
            self.session.world.changes.clear();self.edit_dirty=False
            messagebox.showinfo('保存完成',f'已保存并通过重新读取校验。\n备份：{backup}\n\n进入游戏后，请从「{self.session.slot.name}」对应存档槽读档。')
            self.load_selected(discard_checked=True)
        except Exception as e:self.error(e)

    def refresh_backups(self):
        self.backup_tree.delete(*self.backup_tree.get_children());self.backup_paths={}
        if not self.session or not BACKUPS.exists():return
        for p in sorted(BACKUPS.glob('*/backup.json'),reverse=True):
            try:
                m=json.loads(p.read_text(encoding='utf-8'))
                if Path(m['slot']).resolve()!=self.session.slot:continue
                iid=self.backup_tree.insert('','end',text=p.parent.name,values=(m['time'],m['reason']))
                self.backup_paths[iid]=p.parent
            except (OSError,ValueError,KeyError):continue

    def open_backups(self):BACKUPS.mkdir(exist_ok=True);os.startfile(str(BACKUPS))

    def restore(self):
        if self.busy or not self.session:return
        sel=self.backup_tree.selection()
        if not sel:messagebox.showinfo('选择备份','请先选择要恢复的备份。');return
        p=self.backup_paths[sel[0]]
        if not messagebox.askyesno('恢复备份',f'将恢复当前槽到：\n{p.name}\n\n当前存档会先另行备份。未保存修改将被丢弃。确认恢复？'):return
        try:
            self.session.restore(p,BACKUPS);self.session.world.changes.clear();self.edit_dirty=False
            messagebox.showinfo('恢复完成','备份已恢复，恢复前的状态也已另行备份。');self.load_selected(discard_checked=True)
        except Exception as e:self.error(e)

    def error(self,e):
        self.status.set('操作未完成：'+str(e));messagebox.showerror('操作未完成',str(e),parent=self)
        try:
            with (APP_DIR/'error.log').open('a',encoding='utf-8') as f:f.write(datetime.now().isoformat()+'\n'+traceback.format_exc()+'\n')
        except OSError:pass

    def close(self):
        if self.confirm_discard():self.destroy()

if __name__=='__main__':
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:pass
    Editor().mainloop()
