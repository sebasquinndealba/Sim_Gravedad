import math
import pygame

# Simulador gravitatorio v6.2
WIN_W, WIN_H = 1200, 800
W, H, PANEL, FPS = WIN_W, WIN_H, 330, 60
BG=(12,15,25); PC=(27,31,45); TXT=(235,235,240); MUT=(155,165,185)
BLUE=(70,135,255); RED=(245,70,80); YEL=(255,210,80); GREEN=(105,220,160)
CYAN=(70,240,255); AXIS=(65,70,90); TRAIL=(80,100,150); BORDER=(90,95,115)
G0,GMIN,GMAX=2000.,0.,10000.; C0,CMIN,CMAX=1000.,10.,10000.
SOFT=8.; DT=.01; SUB=5; HIST=120.; EPS=1e-9
SLINGSHOT_SCALE=1.0; SLINGSHOT_MIN_PIXELS=8
# Prediccion aproximada de la trayectoria de la esfera que se lanzara.
PREDICTION_STEPS=600
PREDICTION_DT=0.02
PREDICTION_POINT_EVERY=4
PREDICTION_MAX_SCREEN_DISTANCE=5000
PREDICTION_COLOR=(180,220,255)
G_RECT=pygame.Rect(20,210,290,8); C_RECT=pygame.Rect(20,265,290,8)
CHECK_INSTANT=pygame.Rect(20,295,20,20); CHECK_COLL=pygame.Rect(20,323,20,20)
CHECK_FULL=pygame.Rect(20,351,20,20)


def clamp(v,a,b): return max(a,min(b,v))

class Camera:
    def __init__(self): self.x=self.y=0.; self.zoom=1.
    def center(self): return PANEL+(W-PANEL)/2,H/2
    def to_screen(self,x,y):
        cx,cy=self.center(); return cx+(x-self.x)*self.zoom,cy-(y-self.y)*self.zoom
    def to_world(self,x,y):
        cx,cy=self.center(); return self.x+(x-cx)/self.zoom,self.y-(y-cy)/self.zoom
    def zoom_at(self,pos,f):
        before=self.to_world(*pos); self.zoom=clamp(self.zoom*f,.05,8.)
        after=self.to_world(*pos); self.x+=before[0]-after[0]; self.y+=before[1]-after[1]
    def pan(self,dx,dy): self.x-=dx/self.zoom; self.y+=dy/self.zoom
    def reset(self): self.x=self.y=0.; self.zoom=1.
    def follow(self,b): self.x,self.y=b.x,b.y

class Body:
    nid=1
    def __init__(self,x,y,m,vx,vy,t):
        self.id=Body.nid; Body.nid+=1
        self.x,self.y,self.m,self.vx,self.vy=map(float,(x,y,m,vx,vy))
        self.r=clamp(int(abs(self.m)**(1/3)),4,70); self.trail=[]
        self.created=float(t); self.destroyed=None
        self.history=[(self.created,self.x,self.y,self.m)]
    def record(self,t):
        s=(float(t),self.x,self.y,self.m)
        if self.history and abs(self.history[-1][0]-t)<1e-12:self.history[-1]=s
        else:self.history.append(s)
        while len(self.history)>2 and self.history[1][0]<t-HIST:self.history.pop(0)
    def past(self,t):
        if t<self.created or (self.destroyed is not None and t>=self.destroyed):return None
        if not self.history or t<self.history[0][0]:return None
        if t>=self.history[-1][0]:return self.history[-1][1:]
        lo,hi=0,len(self.history)-1
        while lo+1<hi:
            mid=(lo+hi)//2
            if self.history[mid][0]<=t:lo=mid
            else:hi=mid
        a,b=self.history[lo],self.history[hi]; q=0 if b[0]==a[0] else (t-a[0])/(b[0]-a[0])
        return tuple(a[i]+(b[i]-a[i])*q for i in range(1,4))
    def update(self,ax,ay,dt,t):
        self.vx+=ax*dt; self.vy+=ay*dt; self.x+=self.vx*dt; self.y+=self.vy*dt; self.record(t)
        if not self.trail or math.hypot(self.x-self.trail[-1][0],self.y-self.trail[-1][1])>=.5:self.trail.append((self.x,self.y))
        if len(self.trail)>1500:self.trail.pop(0)
    def draw(self,s,font,cam,trails,vectors,selected):
        x,y=cam.to_screen(self.x,self.y); p=(int(x),int(y)); r=min(100,max(2,int(self.r*math.sqrt(cam.zoom))))
        if trails and len(self.trail)>1:
            pygame.draw.lines(s,TRAIL,False,[tuple(map(int,cam.to_screen(*q))) for q in self.trail],1)
        c=BLUE if self.m>0 else RED; pygame.draw.circle(s,c,p,r); pygame.draw.circle(s,TXT,p,r,2)
        if selected:pygame.draw.circle(s,(100,255,140),p,r+5,2)
        if vectors:
            e=tuple(map(int,cam.to_screen(self.x+self.vx*.5,self.y+self.vy*.5)))
            pygame.draw.line(s,YEL,p,e,2); pygame.draw.circle(s,YEL,e,3)
        s.blit(font.render(f'm={self.m:g}',True,TXT),(p[0]+r+6,p[1]-r))

def source_state(ox,oy,b,t,c,instant):
    if instant:return None if b.destroyed is not None else (b.x,b.y,b.m)
    x,y,m=b.x,b.y,b.m
    for _ in range(4):
        st=b.past(t-math.hypot(x-ox,y-oy)/c)
        if st is None:return None
        x,y,m=st
    return x,y,m

def field(x,y,sources,g,c,t,instant,exclude=None):
    fx=fy=0.
    for b in sources:
        if exclude is b:continue
        st=source_state(x,y,b,t,c,instant)
        if st is None:continue
        sx,sy,m=st; dx,dy=sx-x,sy-y; d2=dx*dx+dy*dy+SOFT*SOFT; k=g*m*d2**-1.5
        fx+=k*dx; fy+=k*dy
    return fx,fy

def merge(bodies,sources,selected,tracked,t):
    again=True
    while again:
        again=False
        for i in range(len(bodies)):
            for j in range(i+1,len(bodies)):
                a,b=bodies[i],bodies[j]
                if (a.x-b.x)**2+(a.y-b.y)**2>(a.r+b.r)**2:continue
                a.record(t);b.record(t);a.destroyed=b.destroyed=t;m=a.m+b.m;new=None
                if abs(m)>=EPS:
                    new=Body((a.m*a.x+b.m*b.x)/m,(a.m*a.y+b.m*b.y)/m,m,(a.m*a.vx+b.m*b.vx)/m,(a.m*a.vy+b.m*b.vy)/m,t)
                    sources.append(new);bodies.append(new)
                if selected in (a,b):selected=new
                if tracked in (a,b):tracked=new
                bodies.remove(a);bodies.remove(b);again=True;break
            if again:break
    return selected,tracked

def text(s,font,msg,x,y,c=TXT):s.blit(font.render(msg,True,c),(x,y))
def checkbox(s,font,rect,label,on):
    c=(100,255,140) if on else BORDER;pygame.draw.rect(s,c,rect,2,border_radius=3)
    if on:
        pygame.draw.line(s,c,(rect.x+4,rect.y+10),(rect.x+9,rect.y+15),3)
        pygame.draw.line(s,c,(rect.x+9,rect.y+15),(rect.x+17,rect.y+4),3)
    text(s,font,label,rect.right+8,rect.y+1,c if on else TXT)
def slider(s,font,rect,label,val,ratio,lo,hi):
    text(s,font,f'{label}: {val}',20,rect.y-22);pygame.draw.rect(s,(75,82,105),rect,border_radius=4)
    pygame.draw.rect(s,(95,180,255),(rect.x,rect.y,int(rect.w*ratio),rect.h),border_radius=4)
    pygame.draw.circle(s,TXT,(int(rect.x+rect.w*ratio),rect.centery),9);text(s,font,lo,rect.x,rect.bottom+3,MUT)
    q=font.render(hi,True,MUT);s.blit(q,(rect.right-q.get_width(),rect.bottom+3))
def sval(mx,rect,a,b,log=False):
    q=clamp((mx-rect.x)/rect.w,0,1)
    return 10**(math.log10(a)+q*(math.log10(b)-math.log10(a))) if log else a+q*(b-a)
def hit_body(bodies,pos,cam):
    for b in reversed(bodies):
        x,y=cam.to_screen(b.x,b.y);r=max(7,int(b.r*math.sqrt(cam.zoom)))
        if (pos[0]-x)**2+(pos[1]-y)**2<=r*r:return b

def draw_field_vectors(s,cam,sources,g,c,t,instant):
    for sy in range(10,H,20):
        for sx in range(PANEL+10,W,20):
            wx,wy=cam.to_world(sx,sy);fx,fy=field(wx,wy,sources,g,c,t,instant);m=math.hypot(fx,fy)
            if m<1e-12:continue
            L=4+math.tanh(m/80)*22;vx,vy=fx/m*L,-fy/m*L
            pygame.draw.line(s,GREEN,(sx-vx/2,sy-vy/2),(sx+vx/2,sy+vy/2),1)

def draw_contours(s,cam,sources,g,c,t,instant):
    step=25;xs=list(range(PANEL,W+step,step));ys=list(range(0,H+step,step));z=[]
    for yy in ys:
        row=[]
        for xx in xs:
            wx,wy=cam.to_world(xx,yy);fx,fy=field(wx,wy,sources,g,c,t,instant);row.append(math.log10(1+math.hypot(fx,fy)))
        z.append(row)
    vals=[v for r in z for v in r]
    if not vals or max(vals)-min(vals)<1e-9:return
    levels=[min(vals)+(max(vals)-min(vals))*(i+1)/10 for i in range(9)]
    colors=[(55,70,130),(60,105,165),(65,145,185),(80,185,170),(145,210,125),(235,205,90)]
    for k,L in enumerate(levels):
        col=colors[min(5,k*6//9)]
        for iy in range(len(ys)-1):
            for ix in range(len(xs)-1):
                p=[(xs[ix],ys[iy]),(xs[ix+1],ys[iy]),(xs[ix+1],ys[iy+1]),(xs[ix],ys[iy+1])]
                v=[z[iy][ix],z[iy][ix+1],z[iy+1][ix+1],z[iy+1][ix]];cuts=[]
                for a,b in ((0,1),(1,2),(2,3),(3,0)):
                    if (v[a]<L)!=(v[b]<L):
                        q=(L-v[a])/(v[b]-v[a]);cuts.append((p[a][0]+(p[b][0]-p[a][0])*q,p[a][1]+(p[b][1]-p[a][1])*q))
                if len(cuts)>=2:pygame.draw.line(s,col,cuts[0],cuts[1],1)
                if len(cuts)==4:pygame.draw.line(s,col,cuts[2],cuts[3],1)

def predict_trajectory(x,y,vx,vy,mass,radius,bodies,sources,g,c,t,instant,collisions,cam):
    """Predice solo la esfera nueva; no modifica cuerpos ni historiales reales."""
    points=[]
    px,py=float(x),float(y)
    pvx,pvy=float(vx),float(vy)
    prediction_time=float(t)
    start_screen=cam.to_screen(px,py)

    for step in range(PREDICTION_STEPS):
        ax,ay=field(px,py,sources,g,c,prediction_time,instant)
        pvx+=ax*PREDICTION_DT
        pvy+=ay*PREDICTION_DT
        px+=pvx*PREDICTION_DT
        py+=pvy*PREDICTION_DT
        prediction_time+=PREDICTION_DT

        if step % PREDICTION_POINT_EVERY == 0:
            sx,sy=cam.to_screen(px,py)
            points.append((int(sx),int(sy)))
            if math.hypot(sx-start_screen[0],sy-start_screen[1])>PREDICTION_MAX_SCREEN_DISTANCE:
                break

        if collisions:
            hit=False
            for body in bodies:
                if (px-body.x)**2+(py-body.y)**2 <= (radius+body.r)**2:
                    hit=True
                    break
            if hit:
                break

    return points


def draw_dotted_trajectory(screen,points):
    """Dibuja puntos progresivamente mas pequenos para representar el futuro."""
    if not points:
        return
    total=max(1,len(points)-1)
    for index,point in enumerate(points):
        progress=index/total
        radius=3 if progress<0.35 else 2
        color=(
            int(PREDICTION_COLOR[0]*(1-0.55*progress)),
            int(PREDICTION_COLOR[1]*(1-0.55*progress)),
            int(PREDICTION_COLOR[2]*(1-0.55*progress)),
        )
        if -5<=point[0]<=W+5 and -5<=point[1]<=H+5:
            pygame.draw.circle(screen,color,point,radius)


def main():
    global W,H
    pygame.init();screen=pygame.display.set_mode((WIN_W,WIN_H));pygame.display.set_caption('Simulador gravitatorio v6.2')
    clock=pygame.time.Clock();font=pygame.font.SysFont('consolas',18);small=pygame.font.SysFont('consolas',14);title=pygame.font.SysFont('consolas',20,True)
    cam=Camera();bodies=[];sources=[];selected=tracked=None;run=True;sim=False
    trails=cm=vectors=collisions=True;instant=full=False;fieldmode=0;g=G0;c=C0;t=0.
    mass,vx,vy='1000','0','0';active=0;drag_g=drag_c=drag_cam=False;last=(0,0)
    sling_active=False; sling_start_screen=None; sling_current_screen=None; sling_start_world=None
    while run:
        frame=clock.tick(FPS)/1000
        for e in pygame.event.get():
            if e.type==pygame.QUIT:run=False
            elif e.type==pygame.KEYDOWN:
                if e.key==pygame.K_ESCAPE:
                    if selected:selected=None
                    else:run=False
                elif e.key==pygame.K_SPACE:sim=not sim
                elif e.key==pygame.K_v:vectors=not vectors
                elif e.key==pygame.K_f:fieldmode=(fieldmode+1)%3
                elif e.key==pygame.K_t:trails=not trails
                elif e.key==pygame.K_m:cm=not cm
                elif e.key==pygame.K_h:tracked=None;cam.reset()
                elif e.key==pygame.K_c:bodies.clear();sources.clear();selected=tracked=None
                elif e.key==pygame.K_r:
                    for b in bodies:b.vx=b.vy=0;b.record(t)
                elif e.key==pygame.K_TAB:active=(active+1)%3
                elif e.key in (pygame.K_DELETE,pygame.K_x) and selected in bodies:
                    selected.record(t);selected.destroyed=t
                    if tracked is selected:tracked=None
                    bodies.remove(selected);selected=None
                elif e.key in (pygame.K_RETURN,pygame.K_KP_ENTER) and selected:
                    try:
                        nm,nx,ny=float(mass),float(vx),float(vy)
                        if abs(nm)<EPS:raise ValueError
                        selected.m,selected.vx,selected.vy=nm,nx,ny;selected.r=clamp(int(abs(nm)**(1/3)),4,70);selected.record(t)
                    except ValueError:pass
                elif e.key==pygame.K_BACKSPACE:
                    if active==0:mass=mass[:-1]
                    elif active==1:vx=vx[:-1]
                    else:vy=vy[:-1]
                elif e.unicode in '-0123456789.eE+':
                    if active==0:mass+=e.unicode
                    elif active==1:vx+=e.unicode
                    else:vy+=e.unicode
            elif e.type==pygame.MOUSEBUTTONDOWN:
                p=e.pos
                if e.button==1:
                    if G_RECT.inflate(10,34).collidepoint(p):drag_g=True;g=sval(p[0],G_RECT,GMIN,GMAX)
                    elif C_RECT.inflate(10,34).collidepoint(p):drag_c=True;c=sval(p[0],C_RECT,CMIN,CMAX,True)
                    elif CHECK_INSTANT.inflate(290,8).collidepoint(p):instant=not instant
                    elif CHECK_COLL.inflate(290,8).collidepoint(p):collisions=not collisions
                    elif CHECK_FULL.inflate(290,8).collidepoint(p):
                        full=not full;screen=pygame.display.set_mode((0,0),pygame.FULLSCREEN) if full else pygame.display.set_mode((WIN_W,WIN_H));W,H=screen.get_size()
                    elif p[0]>PANEL:
                        b=hit_body(bodies,p,cam)
                        if b:
                            selected=tracked=b;mass=f'{b.m:g}';vx=f'{b.vx:g}';vy=f'{b.vy:g}';cam.follow(b)
                        else:
                            # Iniciar creacion tipo resortera en un espacio vacio.
                            try:
                                nm=float(mass)
                                if abs(nm)<EPS:raise ValueError
                                sling_active=True
                                sling_start_screen=p
                                sling_current_screen=p
                                sling_start_world=cam.to_world(*p)
                            except ValueError:
                                sling_active=False
                elif e.button==2:drag_cam=True;last=p
                elif e.button==3 and p[0]>PANEL:selected=hit_body(bodies,p,cam)
            elif e.type==pygame.MOUSEBUTTONUP:
                if e.button==1:
                    drag_g=drag_c=False
                    if sling_active:
                        sling_current_screen=e.pos
                        drag_distance=math.hypot(
                            sling_current_screen[0]-sling_start_screen[0],
                            sling_current_screen[1]-sling_start_screen[1]
                        )
                        try:
                            nm=float(mass)
                            if abs(nm)<EPS:raise ValueError
                            if drag_distance>=SLINGSHOT_MIN_PIXELS:
                                current_world=cam.to_world(*sling_current_screen)
                                launch_vx=(sling_start_world[0]-current_world[0])*SLINGSHOT_SCALE
                                launch_vy=(sling_start_world[1]-current_world[1])*SLINGSHOT_SCALE
                            else:
                                # Un clic normal conserva los campos manuales.
                                launch_vx=float(vx);launch_vy=float(vy)
                            b=Body(sling_start_world[0],sling_start_world[1],nm,launch_vx,launch_vy,t)
                            bodies.append(b);sources.append(b);selected=None
                        except ValueError:
                            pass
                        sling_active=False;sling_start_screen=None;sling_current_screen=None;sling_start_world=None
                elif e.button==2:drag_cam=False
            elif e.type==pygame.MOUSEMOTION:
                if drag_g:g=sval(e.pos[0],G_RECT,GMIN,GMAX)
                if drag_c:c=sval(e.pos[0],C_RECT,CMIN,CMAX,True)
                if sling_active:sling_current_screen=e.pos
                if drag_cam:cam.pan(e.pos[0]-last[0],e.pos[1]-last[1]);last=e.pos
            elif e.type==pygame.MOUSEWHEEL and pygame.mouse.get_pos()[0]>PANEL:cam.zoom_at(pygame.mouse.get_pos(),1.15**e.y)
        keys=pygame.key.get_pressed();pan=500*frame
        if not tracked:
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:cam.pan(pan,0)
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:cam.pan(-pan,0)
            if keys[pygame.K_w] or keys[pygame.K_UP]:cam.pan(0,pan)
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:cam.pan(0,-pan)
        if sim and (bodies or sources):
            dt=DT/SUB
            for _ in range(SUB):
                acc=[field(b.x,b.y,sources,g,c,t,instant,b) for b in bodies];t+=dt
                for b,(ax,ay) in zip(bodies,acc):b.update(ax,ay,dt,t)
                if collisions:selected,tracked=merge(bodies,sources,selected,tracked,t)
            sources[:]=[b for b in sources if b.destroyed is None or b.destroyed>=t-HIST]
        if tracked in bodies:cam.follow(tracked)
        elif tracked is not None:tracked=None
        screen.fill(BG)
        ox,oy=cam.to_screen(0,0)
        if 0<=oy<=H:pygame.draw.line(screen,AXIS,(PANEL,int(oy)),(W,int(oy)))
        if PANEL<=ox<=W:pygame.draw.line(screen,AXIS,(int(ox),0),(int(ox),H))
        if fieldmode==1:draw_field_vectors(screen,cam,sources,g,c,t,instant)
        elif fieldmode==2:draw_contours(screen,cam,sources,g,c,t,instant)
        for b in bodies:b.draw(screen,small,cam,trails,vectors,b is selected)
        # Previsualizacion de la resortera y de la velocidad de lanzamiento.
        if sling_active and sling_start_screen and sling_current_screen:
            start=sling_start_screen;current=sling_current_screen
            current_world=cam.to_world(*current)
            pvx=(sling_start_world[0]-current_world[0])*SLINGSHOT_SCALE
            pvy=(sling_start_world[1]-current_world[1])*SLINGSHOT_SCALE
            speed_preview=math.hypot(pvx,pvy)

            # Trayectoria predictiva punteada. Se calcula con una esfera virtual.
            try:
                prediction_mass=float(mass)
                prediction_radius=clamp(int(abs(prediction_mass)**(1/3)),4,70)
                prediction_points=predict_trajectory(
                    sling_start_world[0],sling_start_world[1],
                    pvx,pvy,prediction_mass,prediction_radius,
                    bodies,sources,g,c,t,instant,collisions,cam
                )
                draw_dotted_trajectory(screen,prediction_points)
            except ValueError:
                pass

            pygame.draw.line(screen,(255,180,80),start,current,3)
            pygame.draw.circle(screen,(255,255,255),start,8,2)
            # La flecha apunta desde la esfera en la direccion real de lanzamiento.
            arrow_end=(start[0]+(start[0]-current[0]),start[1]+(start[1]-current[1]))
            pygame.draw.line(screen,(100,255,140),start,arrow_end,3)
            pygame.draw.circle(screen,(100,255,140),(int(arrow_end[0]),int(arrow_end[1])),5)
            # Caja ordenada junto al cursor. Cada parametro ocupa su propia linea.
            preview_lines = [
                f"Vx: {pvx:.2f}",
                f"Vy: {pvy:.2f}",
                f"Rapidez: {speed_preview:.2f}",
            ]
            preview_surfaces = [small.render(line, True, TXT) for line in preview_lines]
            padding = 8
            line_gap = 3
            box_width = max(surface.get_width() for surface in preview_surfaces) + padding * 2
            box_height = (sum(surface.get_height() for surface in preview_surfaces)
                          + line_gap * (len(preview_surfaces) - 1) + padding * 2)

            # Posicion normal: abajo y a la derecha del cursor.
            box_x = current[0] + 18
            box_y = current[1] + 30

            # Si no cabe, cambia de lado sin cubrir el cursor.
            if box_x + box_width > W - 6:
                box_x = current[0] - box_width - 18
            if box_y + box_height > H - 6:
                box_y = current[1] - box_height - 18
            box_x = max(PANEL + 6, min(box_x, W - box_width - 6))
            box_y = max(6, min(box_y, H - box_height - 6))

            preview_box = pygame.Rect(box_x, box_y, box_width, box_height)
            pygame.draw.rect(screen, (20, 23, 34), preview_box, border_radius=6)
            pygame.draw.rect(screen, (100, 255, 140), preview_box, 2, border_radius=6)

            line_y = box_y + padding
            for surface in preview_surfaces:
                screen.blit(surface, (box_x + padding, line_y))
                line_y += surface.get_height() + line_gap
        if cm and bodies:
            mt=sum(b.m for b in bodies)
            if abs(mt)>EPS:
                cx=sum(b.m*b.x for b in bodies)/mt;cy=sum(b.m*b.y for b in bodies)/mt;sx,sy=map(int,cam.to_screen(cx,cy));pygame.draw.circle(screen,CYAN,(sx,sy),12,2)
        pygame.draw.rect(screen,PC,(0,0,PANEL,H));pygame.draw.line(screen,BORDER,(PANEL,0),(PANEL,H),2)
        text(screen,title,'SIMULADOR GRAVITATORIO V6.2',15,15);text(screen,font,'Estado: EJECUCION' if sim else 'Estado: PAUSA',15,48,(90,255,140) if sim else (255,190,80))
        for i,(lab,val) in enumerate((('Masa',mass),('Velocidad X',vx),('Velocidad Y',vy))):text(screen,font,('> ' if i==active else '  ')+f'{lab}: {val}',15,80+i*32,(100,255,140) if i==active else TXT)
        slider(screen,small,G_RECT,'G',f'{g:.0f}',g/GMAX,'0','10000');cr=(math.log10(c)-1)/3;slider(screen,small,C_RECT,'Velocidad gravedad c',f'{c:.1f}',cr,'10','10000')
        checkbox(screen,small,CHECK_INSTANT,'Propagacion instantanea',instant);checkbox(screen,small,CHECK_COLL,'Colisiones activadas',collisions);checkbox(screen,small,CHECK_FULL,'Pantalla completa',full)
        modes=('oculto','vectorial','contornos');lines=['CONTROLES','Clic masa: seleccionar y seguir','Arrastrar vacio: lanzar esfera',f'F: campo {modes[fieldmode]}','V: vectores | T: trazas | M: CM','DELETE: borrar con retardo','C: limpiar | H: dejar seguimiento','ESPACIO: iniciar/pausar','Rueda: zoom | boton medio: mover']
        yy=390
        for line in lines:text(screen,small,line,15,yy,GREEN if line.startswith('F:') else TXT);yy+=20
        text(screen,small,f'Cuerpos: {len(bodies)}',15,570);text(screen,small,f'Tiempo: {t:.2f} s',15,590);text(screen,small,f'Seguimiento: {"SI" if tracked else "NO"}',15,610)
        mx,my=pygame.mouse.get_pos()
        if mx>PANEL:
            wx,wy=cam.to_world(mx,my);text(screen,small,f'({wx:.2f}, {wy:.2f})',mx+12,my+12)
        pygame.display.flip()
    pygame.quit()

if __name__=='__main__':main()
