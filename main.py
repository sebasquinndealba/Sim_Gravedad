import math
import asyncio
import sys
import pygame

# Simulador gravitatorio v7.0 - escritorio + web/pygbag optimizado
WIN_W, WIN_H = 1200, 800
W, H, PANEL, FPS = WIN_W, WIN_H, 330, 60
IS_WEB = sys.platform == "emscripten"
WEB_FIELD_UPDATE_EVERY = 6
DESKTOP_FIELD_UPDATE_EVERY = 2
WEB_INTENSITY_STEP = 20
DESKTOP_INTENSITY_STEP = 10
WEB_VECTOR_STEP = 30
DESKTOP_VECTOR_STEP = 20
ENERGY_UPDATE_EVERY = 6 if IS_WEB else 2
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
SOLAR_BUTTON=pygame.Rect(20,770,290,25)


def clamp(v,a,b): return max(a,min(b,v))

class Camera:
    def __init__(self): self.x=self.y=0.; self.zoom=1.
    def center(self): return PANEL+(W-PANEL)/2,H/2
    def to_screen(self,x,y):
        cx,cy=self.center(); return cx+(x-self.x)*self.zoom,cy-(y-self.y)*self.zoom
    def to_world(self,x,y):
        cx,cy=self.center(); return self.x+(x-cx)/self.zoom,self.y-(y-cy)/self.zoom
    def zoom_at(self,pos,f):
        before=self.to_world(*pos); self.zoom=clamp(self.zoom*f,.0001,8.)
        after=self.to_world(*pos); self.x+=before[0]-after[0]; self.y+=before[1]-after[1]
    def pan(self,dx,dy): self.x-=dx/self.zoom; self.y+=dy/self.zoom
    def reset(self): self.x=self.y=0.; self.zoom=1.
    def follow(self,b): self.x,self.y=b.x,b.y

class Body:
    nid=1
    def __init__(self,x,y,m,vx,vy,t,fixed=False):
        self.id=Body.nid; Body.nid+=1
        self.x,self.y,self.m,self.vx,self.vy=map(float,(x,y,m,vx,vy))
        self.fixed=bool(fixed)
        if self.fixed:self.vx=self.vy=0.0
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
            trail_color=(135,155,210) if getattr(self,'kinematic_moon',False) else TRAIL
            trail_data=self.trail
            # En WASM limitar la cantidad de vertices renderizados mantiene la
            # misma forma visual sin transformar miles de puntos por cuerpo.
            if IS_WEB and len(trail_data)>500:
                stride=max(1,math.ceil(len(trail_data)/500))
                trail_data=trail_data[::stride]
                if trail_data[-1] is not self.trail[-1]:
                    trail_data=trail_data+[self.trail[-1]]
            pygame.draw.lines(s,trail_color,False,[tuple(map(int,cam.to_screen(*q))) for q in trail_data],1)
        c=BLUE if self.m>0 else RED; pygame.draw.circle(s,c,p,r); pygame.draw.circle(s,TXT,p,r,2)
        if self.fixed:
            pygame.draw.circle(s,YEL,p,r+4,2)
            pygame.draw.line(s,YEL,(p[0]-5,p[1]),(p[0]+5,p[1]),2)
            pygame.draw.line(s,YEL,(p[0],p[1]-5),(p[0],p[1]+5),2)
        if selected:pygame.draw.circle(s,(100,255,140),p,r+7,2)
        if vectors and not self.fixed and not getattr(self,'kinematic_moon',False):
            e=tuple(map(int,cam.to_screen(self.x+self.vx*.5,self.y+self.vy*.5)))
            pygame.draw.line(s,YEL,p,e,2); pygame.draw.circle(s,YEL,e,3)
        if not getattr(self,'kinematic_moon',False):
            s.blit(font.render(getattr(self,'name',f'm={self.m:g}') + (' [FIJA]' if self.fixed else ''),True,TXT),(p[0]+r+6,p[1]-r))

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

def energy_components(bodies, g):
    """Energia newtoniana con el mismo suavizado usado en field()."""
    kinetic = sum(0.5*b.m*(b.vx*b.vx+b.vy*b.vy) for b in bodies)
    potential = 0.0
    for i, a in enumerate(bodies):
        for b in bodies[i+1:]:
            d2 = (a.x-b.x)**2+(a.y-b.y)**2+SOFT**2
            potential -= g*a.m*b.m/math.sqrt(d2)
    return kinetic,potential,kinetic+potential


def verlet_step(bodies, sources, g, c, t, dt, instant):
    """Velocity Verlet. En modo retardado es solo una aproximacion numerica."""
    acc0 = [(0.0,0.0) if b.fixed else field(b.x,b.y,sources,g,c,t,instant,b) for b in bodies]
    for b,(ax,ay) in zip(bodies,acc0):
        if b.fixed:continue
        b.x += b.vx*dt + 0.5*ax*dt*dt
        b.y += b.vy*dt + 0.5*ay*dt*dt
    new_t=t+dt
    # Registrar posiciones provisionales para que las consultas retardadas
    # puedan interpolar hasta el tiempo nuevo sin consultar el futuro.
    if not instant:
        for b in bodies: b.record(new_t)
    acc1 = [(0.0,0.0) if b.fixed else field(b.x,b.y,sources,g,c,new_t,instant,b) for b in bodies]
    for b,(a0,a1) in zip(bodies,zip(acc0,acc1)):
        if b.fixed:
            b.record(new_t)
            continue
        b.vx += 0.5*(a0[0]+a1[0])*dt
        b.vy += 0.5*(a0[1]+a1[1])*dt
        b.record(new_t)
        if not b.trail or math.hypot(b.x-b.trail[-1][0],b.y-b.trail[-1][1])>=0.5:
            b.trail.append((b.x,b.y))
        if len(b.trail)>1500:b.trail.pop(0)
    return new_t


def merge(bodies,sources,selected,tracked,t):
    again=True
    while again:
        again=False
        for i in range(len(bodies)):
            for j in range(i+1,len(bodies)):
                a,b=bodies[i],bodies[j]
                if a.fixed or b.fixed:continue  # Anclajes rigidos: no fusionarlos.
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

def draw_field_vectors(s,cam,sources,g,c,t,instant,step=20):
    for sy in range(10,H,step):
        for sx in range(PANEL+10,W,step):
            wx,wy=cam.to_world(sx,sy);fx,fy=field(wx,wy,sources,g,c,t,instant);m=math.hypot(fx,fy)
            if m<1e-12:continue
            L=4+math.tanh(m/80)*22;vx,vy=fx/m*L,-fy/m*L
            pygame.draw.line(s,GREEN,(sx-vx/2,sy-vy/2),(sx+vx/2,sy+vy/2),1)

def potential_at(x,y,sources,g):
    """Potencial gravitatorio escalar Phi; aceleracion = -grad(Phi)."""
    return -g*sum(b.m/math.sqrt((b.x-x)**2+(b.y-y)**2+SOFT**2)
                  for b in sources if b.destroyed is None)


def mix_color(a,b,f):
    f=clamp(f,0.0,1.0)
    return tuple(int(a[i]+(b[i]-a[i])*f) for i in range(3))


# Paleta de 18 bandas: negro/azul -> cian -> verde -> amarillo -> naranja -> rojo -> magenta.
FIELD_PALETTE = [
    (16,20,39),(27,33,85),(37,50,133),(40,72,175),
    (36,105,198),(29,140,212),(35,173,205),(45,194,167),
    (70,204,112),(117,215,75),(174,221,60),(223,218,64),
    (248,190,65),(250,149,58),(246,102,54),(231,63,75),
    (197,48,120),(157,53,166)
]

def draw_intensity_bands(s,cam,sources,g,c,t,instant,step=10):
    """Isobandas discretas de |a|, con escala logaritmica adaptativa."""
    xs=list(range(PANEL,W,step)); ys=list(range(0,H,step))
    values=[]
    for sy in ys:
        row=[]
        for sx in xs:
            wx,wy=cam.to_world(sx+step/2,sy+step/2)
            fx,fy=field(wx,wy,sources,g,c,t,instant)
            row.append(math.hypot(fx,fy))
        values.append(row)
    positive=sorted(v for row in values for v in row if v>1e-12)
    if not positive:return
    # Percentiles evitan que una singularidad local domine toda la paleta.
    low=max(positive[int(.05*(len(positive)-1))],1e-12)
    high=max(positive[int(.98*(len(positive)-1))],low*1.001)
    llo,lhi=math.log10(low),math.log10(high)
    n=len(FIELD_PALETTE)
    bands=[]
    for iy,row in enumerate(values):
        bandrow=[]
        for ix,v in enumerate(row):
            q=clamp((math.log10(max(v,1e-12))-llo)/(lhi-llo),0,1)
            band=min(n-1,int(q*n))
            bandrow.append(band)
            pygame.draw.rect(s,FIELD_PALETTE[band],(xs[ix],ys[iy],step+1,step+1))
        bands.append(bandrow)
    # Bordes finos entre niveles discretos, como curvas de nivel coloreadas.
    for iy,row in enumerate(bands):
        for ix,b in enumerate(row):
            edge=tuple(max(0,int(v*.60)) for v in FIELD_PALETTE[b])
            if ix and b!=row[ix-1]:
                pygame.draw.line(s,edge,(xs[ix],ys[iy]),(xs[ix],min(H,ys[iy]+step)),1)
            if iy and b!=bands[iy-1][ix]:
                pygame.draw.line(s,edge,(xs[ix],ys[iy]),(min(W,xs[ix]+step),ys[iy]),1)
    # Leyenda con rango numerico de aceleracion gravitatoria.
    bar_x=PANEL+15;bar_y=H-34;bar_w=min(360,W-PANEL-40)
    for i,col in enumerate(FIELD_PALETTE):
        x0=bar_x+round(bar_w*i/n);x1=bar_x+round(bar_w*(i+1)/n)
        pygame.draw.rect(s,col,(x0,bar_y,x1-x0+1,11))
    font=pygame.font.SysFont('consolas',13)
    text(s,font,f'|g| {low:.2g}',bar_x,bar_y-18,TXT)
    text(s,font,f'{high:.2g} (alto)',bar_x+bar_w-100,bar_y-18,TXT)


def predict_trajectory(x,y,vx,vy,mass,radius,bodies,sources,g,c,t,instant,collisions,cam):
    """Predice solo la esfera nueva; no modifica cuerpos ni historiales reales."""
    points=[]
    px,py=float(x),float(y)
    pvx,pvy=float(vx),float(vy)
    prediction_time=float(t)
    start_screen=cam.to_screen(px,py)

    prediction_steps = 360 if IS_WEB else PREDICTION_STEPS
    for step in range(prediction_steps):
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


# Preset: 1 UA = 10000 unidades; 1 ano = 60 s simulados.
# Escala de masas: masa solar = 2000 unidades.
SOLAR_AU = 10000.0
SOLAR_YEAR = 60.0
SOLAR_MASS = 1000000.0
SOLAR_G = (2*math.pi/SOLAR_YEAR)**2 * SOLAR_AU**3 / SOLAR_MASS
SOLAR_DT = 1.0 / FPS  # un segundo simulado por segundo real a 60 FPS
# Nombre, semieje mayor [UA], masa en masas solares, fase inicial [grados]
SOLAR_PLANETS = (
    ('Mercurio', 0.3871, 1.6601e-7, 20),
    ('Venus',    0.7233, 2.4478e-6, 80),
    ('Tierra',   1.0000, 3.0035e-6, 150),
    ('Marte',    1.5237, 3.2272e-7, 225),
    ('Jupiter',  5.2028, 9.5479e-4, 290),
    ('Saturno',  9.5388, 2.8589e-4, 330),
    ('Urano',   19.1914, 4.3662e-5, 55),
    ('Neptuno', 30.0611, 5.1514e-5, 190),
)

# Lunas principales con semieje mayor aproximado (km) y periodo sidereo (dias).
# Las lunas son objetos cinematicos: no se integran como cuerpos N para evitar
# aliasing temporal (Fobos completa una orbita en ~0.052 s simulados).
# Datos de referencia: NASA/JPL satellite mean elements, aproximaciones 2D.
# Las lunas no enumeradas pueden incorporarse mediante moons_extra.csv.
MOON_DATA = {
 'Tierra': [('Luna',384400,27.3217)],
 'Marte': [('Fobos',9376,0.31891),('Deimos',23463,1.26244)],
 'Jupiter': [('Metis',128000,0.29478),('Adrastea',129000,0.29826),('Amaltea',181400,0.49818),('Tebe',221900,0.6745),('Io',421800,1.76914),('Europa',671100,3.55118),('Ganimedes',1070400,7.15455),('Calisto',1882700,16.68902),('Himalia',11461000,250.56),('Elara',11741000,259.64),('Pasifae',23624000,-743.6),('Sinope',23939000,-758.9)],
 'Saturno': [('Pan',133584,0.57505),('Dafnis',136505,0.59408),('Atlas',137670,0.60169),('Prometeo',139380,0.61299),('Pandora',141720,0.62850),('Epimeteo',151410,0.69433),('Jano',151460,0.69466),('Mimas',185539,0.94242),('Encelado',238042,1.37022),('Tetis',294672,1.88780),('Dione',377415,2.73692),('Rea',527068,4.51750),('Titan',1221870,15.94542),('Hiperion',1481000,21.2766),('Japeto',3560820,79.3215),('Febe',12952000,-550.48)],
 'Urano': [('Cordelia',49752,0.33503),('Ofelia',53764,0.3764),('Bianca',59166,0.43458),('Crésida',61767,0.46357),('Desdemona',62658,0.47365),('Julieta',64358,0.49307),('Porcia',66097,0.5132),('Rosalinda',69927,0.55846),('Belinda',75255,0.62353),('Puck',86004,0.76183),('Miranda',129390,1.41348),('Ariel',191020,2.52038),('Umbriel',266000,4.14418),('Titania',435910,8.70587),('Oberon',583520,13.4632),('Sycorax',12179000,-1288.38)],
 'Neptuno': [('Nayade',48227,0.29440),('Talasa',50075,0.31148),('Despina',52526,0.33466),('Galatea',61953,0.42875),('Larisa',73548,0.55465),('Hipocampo',105284,0.9362),('Proteo',117647,1.12231),('Triton',354759,-5.87685),('Nereida',5513818,360.136),('Halimede',16611000,-1879.7),('Sao',22228000,2912.7),('Laomedeia',23567000,3171.0),('Neso',48387000,-9740.7)]
}
SOLAR_KM_PER_UNIT = 149597870.7 / SOLAR_AU
SOLAR_DAY = SOLAR_YEAR / 365.25636

def moon_catalog():
    """Carga opcional de satelites adicionales sin conexion a internet.
    CSV: planeta,nombre,semieje_km,periodo_dias (negativo=retrogrado).
    """
    import csv
    from pathlib import Path
    data={k:list(v) for k,v in MOON_DATA.items()}
    file=Path(__file__).with_name('moons_extra.csv')
    if file.exists():
        with file.open(encoding='utf-8-sig',newline='') as fh:
            for row in csv.DictReader(fh):
                try:
                    host=row['planeta'].strip()
                    if host not in data:continue
                    item=(row['nombre'].strip(),float(row['semieje_km']),float(row['periodo_dias']))
                    if not item[0] or not item[1]>0 or not item[2]:continue
                    data[host]=[m for m in data[host] if m[0]!=item[0]]+[item]
                except (KeyError,ValueError):continue
    return data

def place_moons(bodies,t):
    """Actualiza las lunas cinematicas y conserva una traza de su recorrido.

    La traza se guarda en coordenadas globales, de modo que al seguir al planeta
    se ve la orbita de la luna alrededor de este y, en una vista heliocentrica,
    tambien queda registrada la trayectoria compuesta planeta+luna.
    """
    for b in bodies:
        if not getattr(b,'kinematic_moon',False):continue
        host=b.moon_host
        theta=b.moon_phase + 2*math.pi*t/b.moon_period
        r=b.moon_radius
        omega=2*math.pi/b.moon_period
        old_x,old_y=b.x,b.y
        b.x=host.x+r*math.cos(theta);b.y=host.y+r*math.sin(theta)
        b.vx=host.vx-r*omega*math.sin(theta)
        b.vy=host.vy+r*omega*math.cos(theta)
        b.history=[(t,b.x,b.y,b.m)]

        # Las lunas no pasan por verlet_step(), por lo que su traza debe
        # acumularse aqui. El umbral se adapta al tamano de la orbita para
        # mantener curvas suaves tanto en satelites cercanos como lejanos.
        min_step=max(0.02,min(2.0,abs(r)*0.015))
        if (not b.trail or
            math.hypot(b.x-b.trail[-1][0],b.y-b.trail[-1][1])>=min_step):
            b.trail.append((b.x,b.y))
        moon_trail_limit=1400 if IS_WEB else 3000
        if len(b.trail)>moon_trail_limit:
            b.trail.pop(0)

def append_moons(bodies):
    planets={getattr(b,'name',''):b for b in bodies}
    catalog=moon_catalog()
    for host_name,items in catalog.items():
        host=planets[host_name]
        for index,(name,km,days) in enumerate(items):
            b=Body(host.x,host.y,0.,0.,0.,0.)
            b.name=name;b.kinematic_moon=True;b.moon_host=host
            b.moon_radius=km/SOLAR_KM_PER_UNIT
            b.moon_period=days*SOLAR_DAY
            b.moon_phase=2*math.pi*((index*.61803398875)%1)
            b.r=2
            bodies.append(b)
    place_moons(bodies,0.)

def load_solar_system():
    """Orbitas iniciales circulares coplanares; velocidades heliocentricas.
    Se corrige el momento total para que el baricentro parta en reposo.
    """
    sun=Body(0,0,SOLAR_MASS,0,0,0)
    sun.name='Sol'
    result=[sun]
    for name, au, solar_masses, degrees in SOLAR_PLANETS:
        r=au*SOLAR_AU
        theta=math.radians(degrees)
        speed=math.sqrt(SOLAR_G*SOLAR_MASS/r)
        b=Body(r*math.cos(theta),r*math.sin(theta),
               SOLAR_MASS*solar_masses,
               -speed*math.sin(theta),speed*math.cos(theta),0)
        b.name=name
        result.append(b)
    total_mass=sum(b.m for b in result)
    cx=sum(b.m*b.x for b in result)/total_mass
    cy=sum(b.m*b.y for b in result)/total_mass
    cvx=sum(b.m*b.vx for b in result)/total_mass
    cvy=sum(b.m*b.vy for b in result)/total_mass
    for b in result:
        b.x-=cx; b.y-=cy
        b.vx-=cvx; b.vy-=cvy
        b.history=[(0.,b.x,b.y,b.m)]
    append_moons(result)
    return result


def draw_solar_orbits(screen, cam, bodies):
    """Orbitas circulares de referencia en el marco heliocentrico inicial."""
    sun=next((b for b in bodies if getattr(b,'name',None)=='Sol'),None)
    if sun is None:return
    # Referencias ideales, no trayectorias futuras calculadas del sistema N-cuerpos.
    colors=((125,125,145),(190,155,110),(90,175,240),(205,120,95),
            (210,170,105),(185,170,125),(100,200,215),(110,130,230))
    old_clip=screen.get_clip()
    screen.set_clip(pygame.Rect(PANEL,0,W-PANEL,H))
    for (_,au,_,_),color in zip(SOLAR_PLANETS,colors):
        radius=au*SOLAR_AU
        # Los circulos se dibujan con segmentos; funciona incluso con zoom muy pequeno.
        n=240
        points=[cam.to_screen(sun.x+radius*math.cos(2*math.pi*i/n),
                              sun.y+radius*math.sin(2*math.pi*i/n)) for i in range(n)]
        pygame.draw.aalines(screen,color,True,points)
    screen.set_clip(old_clip)


def solar_button(screen,font,mouse):
    hover=SOLAR_BUTTON.collidepoint(mouse)
    pygame.draw.rect(screen,(48,104,150) if hover else (42,75,113),SOLAR_BUTTON,border_radius=5)
    pygame.draw.rect(screen,(100,180,230),SOLAR_BUTTON,2,border_radius=5)
    label=font.render('CARGAR SISTEMA SOLAR (P)',True,TXT)
    screen.blit(label,label.get_rect(center=SOLAR_BUTTON.center))


def create_display(fullscreen=False):
    """Crea solo la ventana/canvas fisico.

    La simulacion NO dibuja directamente aqui. Todo se renderiza primero en
    LOGICAL_W x LOGICAL_H y luego se escala manualmente. Esto evita depender
    de pygame.SCALED, cuyo remapeo de mouse puede quedar desincronizado en
    pygbag/navegadores.
    """
    if fullscreen:
        return pygame.display.set_mode((0,0), pygame.FULLSCREEN)
    return pygame.display.set_mode((WIN_W,WIN_H), pygame.RESIZABLE)


def viewport_for(display_surface):
    """Rectangulo del canvas logico dentro de la ventana, conservando aspecto."""
    dw,dh=display_surface.get_size()
    if dw<=0 or dh<=0:
        return pygame.Rect(0,0,WIN_W,WIN_H),1.0
    scale=min(dw/WIN_W,dh/WIN_H)
    vw=max(1,int(round(WIN_W*scale)))
    vh=max(1,int(round(WIN_H*scale)))
    vx=(dw-vw)//2
    vy=(dh-vh)//2
    return pygame.Rect(vx,vy,vw,vh),scale


def physical_to_logical(pos,display_surface):
    """Convierte coordenadas reales del canvas a las 1200x800 de la UI."""
    view,scale=viewport_for(display_surface)
    if scale<=0:
        return (0,0)
    x=(pos[0]-view.x)/scale
    y=(pos[1]-view.y)/scale
    return (clamp(x,0,WIN_W-1),clamp(y,0,WIN_H-1))


def present_logical(display_surface,logical_surface):
    """Escala el frame logico al canvas fisico con letterboxing."""
    view,_=viewport_for(display_surface)
    display_surface.fill((0,0,0))
    if view.size==(WIN_W,WIN_H):
        display_surface.blit(logical_surface,view.topleft)
    else:
        scaled=pygame.transform.scale(logical_surface,view.size)
        display_surface.blit(scaled,view.topleft)
    pygame.display.flip()


async def main():
    pygame.init();display=create_display(False);screen=pygame.Surface((WIN_W,WIN_H));pygame.display.set_caption('Simulador gravitatorio v7.1')
    clock=pygame.time.Clock();font=pygame.font.SysFont('consolas',18);small=pygame.font.SysFont('consolas',14);title=pygame.font.SysFont('consolas',20,True)
    cam=Camera();bodies=[];sources=[];selected=tracked=None;run=True;sim=False
    trails=cm=vectors=collisions=True;instant=True;full=False;fieldmode=0;g=G0;c=C0;t=0.
    mass,vx,vy='1000','0','0';active=0;drag_g=drag_c=drag_cam=False;last=(0,0)
    energy_reference=None;energy_signature=None;solar_mode=False
    sling_active=False; sling_start_screen=None; sling_current_screen=None; sling_start_world=None
    g_slider_max=GMAX
    frame_index=0
    field_cache=None
    field_cache_mode=None
    field_cache_due=True
    field_update_every=WEB_FIELD_UPDATE_EVERY if IS_WEB else DESKTOP_FIELD_UPDATE_EVERY
    intensity_step=WEB_INTENSITY_STEP if IS_WEB else DESKTOP_INTENSITY_STEP
    vector_step=WEB_VECTOR_STEP if IS_WEB else DESKTOP_VECTOR_STEP
    energy_cache=(0.0,0.0,0.0,0.0)
    energy_cache_signature=None
    def activate_solar():
        nonlocal bodies,sources,selected,tracked,sim,t,g,instant,collisions,solar_mode
        nonlocal mass,vx,vy,energy_reference,energy_signature,sling_active
        nonlocal sling_start_screen,sling_current_screen,sling_start_world,g_slider_max,field_cache_due
        bodies=load_solar_system();sources=[b for b in bodies if not getattr(b,'kinematic_moon',False)]
        selected=tracked=None;sim=False;t=0.0
        g=SOLAR_G;g_slider_max=max(GMAX,math.ceil(SOLAR_G/1000)*1000)
        instant=True;collisions=False;solar_mode=True
        cam.reset();cam.zoom=0.00125
        mass,vx,vy='1000','0','0'
        energy_reference=None;energy_signature=None
        sling_active=False;sling_start_screen=sling_current_screen=sling_start_world=None
        field_cache_due=True
    while run:
        frame=clock.tick(FPS)/1000
        frame_index += 1
        for e in pygame.event.get():
            if e.type==pygame.QUIT:run=False
            elif e.type==pygame.KEYDOWN:
                if e.key==pygame.K_ESCAPE:
                    if selected:selected=None
                    else:run=False
                elif e.key==pygame.K_p:activate_solar()
                elif e.key==pygame.K_SPACE:sim=not sim
                elif e.key==pygame.K_v:vectors=not vectors
                elif e.key==pygame.K_f:fieldmode=(fieldmode+1)%3;field_cache_due=True
                elif e.key==pygame.K_t:trails=not trails
                elif e.key==pygame.K_m:cm=not cm
                elif e.key==pygame.K_h:tracked=None;cam.reset()
                elif e.key==pygame.K_c:bodies.clear();sources.clear();selected=tracked=None
                elif e.key==pygame.K_r:
                    for b in bodies:b.vx=b.vy=0;b.record(t)
                    energy_reference=None
                elif e.key==pygame.K_TAB:active=(active+1)%3
                elif e.key in (pygame.K_DELETE,pygame.K_x) and selected in bodies:
                    selected.record(t);selected.destroyed=t
                    if tracked is selected:tracked=None
                    bodies.remove(selected);selected=None
                elif e.key in (pygame.K_RETURN,pygame.K_KP_ENTER) and selected:
                    try:
                        nm,nx,ny=float(mass),float(vx),float(vy)
                        if not math.isfinite(nm) or abs(nm)<EPS:raise ValueError
                        selected.m=nm
                        selected.vx,selected.vy=(0.,0.) if selected.fixed else (nx,ny)
                        selected.r=clamp(int(abs(nm)**(1/3)),4,70);selected.record(t)
                        energy_reference=None
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
                p=physical_to_logical(e.pos,display)
                if e.button==1:
                    if SOLAR_BUTTON.collidepoint(p):activate_solar()
                    elif G_RECT.inflate(10,34).collidepoint(p):drag_g=True;g=sval(p[0],G_RECT,GMIN,g_slider_max);field_cache_due=True
                    elif C_RECT.inflate(10,30).collidepoint(p):drag_c=True;c=sval(p[0],C_RECT,CMIN,CMAX,True);field_cache_due=True
                    elif CHECK_INSTANT.inflate(290,8).collidepoint(p):instant=not instant;energy_reference=None;field_cache_due=True
                    elif CHECK_COLL.inflate(290,8).collidepoint(p):collisions=not collisions
                    elif CHECK_FULL.inflate(290,8).collidepoint(p):
                        full=not full;display=create_display(full);field_cache_due=True
                    elif p[0]>PANEL:
                        b=hit_body(bodies,p,cam)
                        if b:
                            selected=tracked=b;mass=f'{b.m:g}';vx=f'{b.vx:g}';vy=f'{b.vy:g}';cam.follow(b)
                        else:
                            # Iniciar creacion tipo resortera en un espacio vacio.
                            try:
                                nm=float(mass)
                                if not math.isfinite(nm) or abs(nm)<EPS:raise ValueError
                                sling_active=True
                                sling_start_screen=p
                                sling_current_screen=p
                                sling_start_world=cam.to_world(*p)
                            except ValueError:
                                sling_active=False
                elif e.button==2:drag_cam=True;last=p
                elif e.button==3 and p[0]>PANEL:
                    # Clic derecho en vacio: crear masa anclada a coordenadas mundo.
                    selected=hit_body(bodies,p,cam)
                    if selected is None:
                        try:
                            nm=float(mass)
                            if not math.isfinite(nm) or abs(nm)<EPS:raise ValueError
                            wx,wy=cam.to_world(*p)
                            anchor=Body(wx,wy,nm,0.,0.,t,fixed=True)
                            bodies.append(anchor);sources.append(anchor)
                        except ValueError:pass
            elif e.type==pygame.MOUSEBUTTONUP:
                if e.button==1:
                    drag_g=drag_c=False
                    if sling_active:
                        sling_current_screen=physical_to_logical(e.pos,display)
                        drag_distance=math.hypot(
                            sling_current_screen[0]-sling_start_screen[0],
                            sling_current_screen[1]-sling_start_screen[1]
                        )
                        try:
                            nm=float(mass)
                            if not math.isfinite(nm) or abs(nm)<EPS:raise ValueError
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
                mp=physical_to_logical(e.pos,display)
                if drag_g:g=sval(mp[0],G_RECT,GMIN,g_slider_max);field_cache_due=True
                if drag_c:c=sval(mp[0],C_RECT,CMIN,CMAX,True);field_cache_due=True
                if sling_active:sling_current_screen=mp
                if drag_cam:cam.pan(mp[0]-last[0],mp[1]-last[1]);last=mp;field_cache_due=True
            elif e.type==pygame.MOUSEWHEEL:
                mp=physical_to_logical(pygame.mouse.get_pos(),display)
                if mp[0]>PANEL:
                    cam.zoom_at(mp,1.15**e.y);field_cache_due=True
        keys=pygame.key.get_pressed();pan=500*frame
        if not tracked:
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:cam.pan(pan,0);field_cache_due=True
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:cam.pan(-pan,0);field_cache_due=True
            if keys[pygame.K_w] or keys[pygame.K_UP]:cam.pan(0,pan);field_cache_due=True
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:cam.pan(0,-pan);field_cache_due=True
        if sim and (bodies or sources):
            # En el preset solar 60 s reales ~= 1 ano incluso si WebAssembly cae de 60 FPS.
            # Se limita frame para evitar saltos enormes al volver de una pestaña suspendida.
            sim_frame_dt=min(frame,0.05) if solar_mode else DT
            dt=sim_frame_dt/SUB
            for _ in range(SUB):
                t=verlet_step([b for b in bodies if not getattr(b,'kinematic_moon',False)],sources,g,c,t,dt,instant)
                if solar_mode:place_moons(bodies,t)
                if collisions:selected,tracked=merge([b for b in bodies if not getattr(b,'kinematic_moon',False)],sources,selected,tracked,t)
            sources[:]=[b for b in sources if b.destroyed is None or b.destroyed>=t-HIST]
        if tracked in bodies:cam.follow(tracked)
        elif tracked is not None:tracked=None
        screen.fill(BG)
        ox,oy=cam.to_screen(0,0)
        if 0<=oy<=H:pygame.draw.line(screen,AXIS,(PANEL,int(oy)),(W,int(oy)))
        if PANEL<=ox<=W:pygame.draw.line(screen,AXIS,(int(ox),0),(int(ox),H))
        if fieldmode:
            if (field_cache is None or field_cache_mode!=fieldmode or field_cache_due
                    or frame_index % field_update_every == 0):
                field_cache=pygame.Surface((W,H),pygame.SRCALPHA)
                if fieldmode==1:
                    draw_field_vectors(field_cache,cam,sources,g,c,t,instant,vector_step)
                else:
                    draw_intensity_bands(field_cache,cam,sources,g,c,t,instant,intensity_step)
                field_cache_mode=fieldmode
                field_cache_due=False
            screen.blit(field_cache,(0,0))
        else:
            field_cache=None;field_cache_mode=None
        if solar_mode:draw_solar_orbits(screen,cam,bodies)
        for b in bodies:
            is_moon=getattr(b,'kinematic_moon',False)
            # Las trazas lunares se muestran al alcanzar una escala util.
            # El cuerpo puede ocultarse cuando su orbita ocupa menos de una
            # fraccion de pixel, pero la traza no se desactiva por ser luna.
            if is_moon and cam.zoom*b.moon_radius < 0.15:
                continue
            b.draw(screen,small,cam,trails,vectors,b is selected)
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
        text(screen,title,'SIMULADOR GRAVITATORIO V7.1',15,15);text(screen,font,'Estado: EJECUCION' if sim else 'Estado: PAUSA',15,48,(90,255,140) if sim else (255,190,80))
        for i,(lab,val) in enumerate((('Masa',mass),('Velocidad X',vx),('Velocidad Y',vy))):text(screen,font,('> ' if i==active else '  ')+f'{lab}: {val}',15,80+i*32,(100,255,140) if i==active else TXT)
        slider(screen,small,G_RECT,'G',f'{g:.4f}',clamp(g/g_slider_max,0,1),'0',f'{g_slider_max:g}')
        cr=(math.log10(c)-math.log10(CMIN))/(math.log10(CMAX)-math.log10(CMIN))
        slider(screen,small,C_RECT,'Propagacion c',f'{c:.1f}',cr,'10','10000')
        checkbox(screen,small,CHECK_INSTANT,'Propagacion instantanea',instant)
        checkbox(screen,small,CHECK_COLL,'Colisiones activadas',collisions);checkbox(screen,small,CHECK_FULL,'Pantalla completa',full)
        modes=('oculto','vectorial','isobandas |g|');lines=['CONTROLES','Clic masa: seleccionar y seguir','Clic derecho vacio: masa FIJA','Arrastrar vacio: lanzar esfera','P: cargar Sistema Solar',f'F: campo {modes[fieldmode]}','V: vectores | T: trazas | M: CM','DELETE: borrar con retardo','C: limpiar | H: dejar seguimiento','ESPACIO: iniciar/pausar','Rueda: zoom | boton medio: mover']
        yy=375
        for line in lines:text(screen,small,line,15,yy,GREEN if line.startswith('F:') else TXT);yy+=17
        text(screen,small,f'Cuerpos: {len(bodies)} (lunas: {sum(getattr(b,"kinematic_moon",False) for b in bodies)})',15,570);text(screen,small,f'Tiempo: {t:.2f} s' + (f' | {t/60:.3f} anos' if solar_mode else ''),15,590);text(screen,small,f'Seguimiento: {"SI" if tracked else "NO"}',15,610)
        # Valores absolutos siempre visibles; error solo en tramos conservativos.
        signature=(tuple((b.id,b.m,b.fixed) for b in bodies if not getattr(b,'kinematic_moon',False)),g,collisions,instant,c if not instant else None)
        if signature!=energy_signature or energy_reference is None or frame_index % ENERGY_UPDATE_EVERY == 0:
            ek,ep,et=energy_components([b for b in bodies if not getattr(b,'kinematic_moon',False)],g)
            if signature!=energy_signature or energy_reference is None:
                energy_reference=et
            error=100*(et-energy_reference)/max(abs(energy_reference),1e-12)
            energy_cache=(ek,ep,et,error)
            energy_signature=signature
        else:
            ek,ep,et,error=energy_cache
        text(screen,small,f'E cinetica:  {ek:.6g}',15,640)
        text(screen,small,f'E potencial: {ep:.6g}',15,660)
        text(screen,small,f'E total:     {et:.6g}',15,680)
        if not collisions and instant:
            text(screen,small,f'Delta E: {error:+.5f}%',15,700,GREEN if abs(error)<0.1 else YEL)
        else:
            text(screen,small,'Delta E: n/a (retardo/colision)',15,700,MUT)
        text(screen,small,('Solar: 1 UA=10000 | 1 ano=60 s' if solar_mode else 'Unidades internas del simulador'),15,727,MUT)
        text(screen,small,'Fijas: restriccion externa' + (' | WEB optimizado' if IS_WEB else ''),15,747,MUT)
        logical_mouse=physical_to_logical(pygame.mouse.get_pos(),display)
        solar_button(screen,small,logical_mouse)
        mx,my=logical_mouse
        if mx>PANEL:
            wx,wy=cam.to_world(mx,my);text(screen,small,f'({wx:.2f}, {wy:.2f})',mx+12,my+12)
        present_logical(display,screen)
        # Obligatorio en pygbag: devuelve control al navegador en cada frame.
        await asyncio.sleep(0)
    if not IS_WEB:
        pygame.quit()

if __name__=='__main__':
    asyncio.run(main())