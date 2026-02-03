import pygame
import sys
import random
import math
from dataclasses import dataclass, field

# --- CONFIGURATION ---
WINDOW_WIDTH = 640
WINDOW_HEIGHT = 480
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 240
FPS = 60

# Colors
COLOR_BG = (20, 20, 30)
COLOR_WALL = (100, 100, 120)
COLOR_PLAYER = (230, 50, 50)  # Red
COLOR_MONSTER = (50, 200, 50) # Green
COLOR_GHOST = (200, 200, 255) # Pale Blue
COLOR_SHADOW = (0, 0, 0, 100) # Semi-transparent black

# --- ECS CORE ---
class ECSManager:
    def __init__(self):
        self.next_entity_id = 0
        self.components = {} 
        self.entities_to_destroy = []

    def create_entity(self):
        entity = self.next_entity_id
        self.next_entity_id += 1
        return entity

    def add_component(self, entity, component):
        comp_type = type(component)
        if comp_type not in self.components:
            self.components[comp_type] = {}
        self.components[comp_type][entity] = component

    def get_component(self, entity, comp_type):
        return self.components.get(comp_type, {}).get(entity)

    def get_entities_with(self, *comp_types):
        if not comp_types: return []
        entities = set(self.components.get(comp_types[0], {}).keys())
        for ct in comp_types[1:]:
            entities &= set(self.components.get(ct, {}).keys())
        return list(entities)

    def destroy_entity(self, entity):
        self.entities_to_destroy.append(entity)

    def process_destruction(self):
        for entity in self.entities_to_destroy:
            for ct in self.components:
                if entity in self.components[ct]:
                    del self.components[ct][entity]
        self.entities_to_destroy.clear()

# --- COMPONENTS (DATA) ---

@dataclass
class Transform:
    x: float
    y: float
    width: int = 16
    height: int = 16

@dataclass
class RigidBody:
    """Physics properties for movement feeling"""
    velocity: pygame.math.Vector2 = field(default_factory=lambda: pygame.math.Vector2(0, 0))
    acceleration: pygame.math.Vector2 = field(default_factory=lambda: pygame.math.Vector2(0, 0))
    friction: float = 10.0
    max_speed: float = 80.0

@dataclass
class MovementState:
    """Syncs Physics with Animation"""
    current_state: str = "IDLE"     # IDLE, WALK
    facing: str = "DOWN"            # DOWN, UP, LEFT, RIGHT

@dataclass
class Collider:
    is_solid: bool = True
    tag: str = "default"

@dataclass
class PaperSprite:
    """Advanced Flipbook Component"""
    animations: dict = field(default_factory=dict) # { "WALK_DOWN": [surf1, surf2] }
    
    current_anim: str = "default"
    frame_index: int = 0
    frame_timer: float = 0.0
    
    frame_duration: float = 0.15
    playback_speed: float = 1.0
    
    # Modes: "LOOP", "ONCE", "PINGPONG"
    loop_mode: str = "LOOP"
    _ping_pong_direction: int = 1
    
    # Visuals
    flip_x: bool = False
    opacity: int = 255
    rotation: float = 0.0
    scale: float = 1.0
    offset_y: int = -4 # Anchor to feet
    z_index: int = 0

@dataclass
class AIBehavior:
    state: str = "PATROL"
    patrol_points: list = field(default_factory=list)
    patrol_index: int = 0
    wait_timer: float = 0.0

@dataclass
class InputControl:
    pass

# --- SYSTEMS (LOGIC) ---

class InputSystem:
    def __init__(self, ecs):
        self.ecs = ecs

    def update(self):
        entities = self.ecs.get_entities_with(InputControl, RigidBody, MovementState)
        keys = pygame.key.get_pressed()
        
        for entity in entities:
            rb = self.ecs.get_component(entity, RigidBody)
            state = self.ecs.get_component(entity, MovementState)
            
            # Input Vector
            input_vec = pygame.math.Vector2(0, 0)
            if keys[pygame.K_LEFT]: input_vec.x = -1
            if keys[pygame.K_RIGHT]: input_vec.x = 1
            if keys[pygame.K_UP]: input_vec.y = -1
            if keys[pygame.K_DOWN]: input_vec.y = 1

            # Normalize and Apply to Acceleration
            if input_vec.length() > 0:
                input_vec = input_vec.normalize()
                rb.acceleration = input_vec * (rb.max_speed * 10) # High accel for snappy feel
                
                # Update State
                state.current_state = "WALK"
                if input_vec.x != 0:
                    state.facing = "RIGHT" if input_vec.x > 0 else "LEFT"
                elif input_vec.y != 0:
                    state.facing = "DOWN" if input_vec.y > 0 else "UP"
            else:
                state.current_state = "IDLE"

class AISystem:
    def __init__(self, ecs):
        self.ecs = ecs

    def update(self, dt):
        entities = self.ecs.get_entities_with(AIBehavior, RigidBody, Transform, MovementState)
        for entity in entities:
            ai = self.ecs.get_component(entity, AIBehavior)
            pos = self.ecs.get_component(entity, Transform)
            rb = self.ecs.get_component(entity, RigidBody)
            state = self.ecs.get_component(entity, MovementState)

            if ai.state == "PATROL" and ai.patrol_points:
                target = ai.patrol_points[ai.patrol_index]
                target_vec = pygame.math.Vector2(target[0], target[1])
                current_vec = pygame.math.Vector2(pos.x, pos.y)
                
                dist = current_vec.distance_to(target_vec)
                
                if dist < 5:
                    # Reached point, wait then go to next
                    ai.wait_timer += dt
                    state.current_state = "IDLE"
                    if ai.wait_timer > 1.0:
                        ai.wait_timer = 0
                        ai.patrol_index = (ai.patrol_index + 1) % len(ai.patrol_points)
                else:
                    # Move towards point
                    direction = (target_vec - current_vec).normalize()
                    rb.acceleration = direction * (rb.max_speed * 5)
                    
                    state.current_state = "WALK"
                    if abs(direction.x) > abs(direction.y):
                        state.facing = "RIGHT" if direction.x > 0 else "LEFT"
                    else:
                        state.facing = "DOWN" if direction.y > 0 else "UP"

class PhysicsSystem:
    def __init__(self, ecs):
        self.ecs = ecs

    def update(self, dt):
        movables = self.ecs.get_entities_with(Transform, RigidBody)
        walls = self.ecs.get_entities_with(Transform, Collider)
        
        for entity in movables:
            rb = self.ecs.get_component(entity, RigidBody)
            pos = self.ecs.get_component(entity, Transform)
            
            # 1. Integrate Acceleration -> Velocity
            if rb.acceleration.length() > 0:
                rb.velocity += rb.acceleration * dt
            else:
                # Friction
                if rb.velocity.length() > 0:
                    friction_vec = rb.velocity.normalize() * rb.friction * 50 * dt
                    if rb.velocity.length() < friction_vec.length():
                        rb.velocity.update(0,0)
                    else:
                        rb.velocity -= friction_vec
            
            # Clamp Speed
            if rb.velocity.length() > rb.max_speed:
                rb.velocity.scale_to_length(rb.max_speed)
            
            # Reset Accel
            rb.acceleration.update(0,0)

            # 2. Movement & Collision (X Axis)
            pos.x += rb.velocity.x * dt
            entity_rect_x = pygame.Rect(pos.x, pos.y, pos.width, pos.height)
            
            for wall in walls:
                if wall == entity: continue
                wall_t = self.ecs.get_component(wall, Transform)
                wall_c = self.ecs.get_component(wall, Collider)
                if not wall_c.is_solid: continue
                
                wall_rect = pygame.Rect(wall_t.x, wall_t.y, wall_t.width, wall_t.height)
                if entity_rect_x.colliderect(wall_rect):
                    if rb.velocity.x > 0: pos.x = wall_rect.left - pos.width
                    if rb.velocity.x < 0: pos.x = wall_rect.right
                    rb.velocity.x = 0

            # 3. Movement & Collision (Y Axis)
            pos.y += rb.velocity.y * dt
            entity_rect_y = pygame.Rect(pos.x, pos.y, pos.width, pos.height)
            
            for wall in walls:
                if wall == entity: continue
                wall_t = self.ecs.get_component(wall, Transform)
                wall_c = self.ecs.get_component(wall, Collider)
                if not wall_c.is_solid: continue
                
                wall_rect = pygame.Rect(wall_t.x, wall_t.y, wall_t.width, wall_t.height)
                if entity_rect_y.colliderect(wall_rect):
                    if rb.velocity.y > 0: pos.y = wall_rect.top - pos.height
                    if rb.velocity.y < 0: pos.y = wall_rect.bottom
                    rb.velocity.y = 0

class AnimationSystem:
    def __init__(self, ecs):
        self.ecs = ecs

    def update(self, dt):
        # 1. State Mapping (MovementState -> PaperSprite current_anim)
        # Only for entities that have BOTH components
        controlled_entities = self.ecs.get_entities_with(MovementState, PaperSprite)
        for entity in controlled_entities:
            state = self.ecs.get_component(entity, MovementState)
            anim = self.ecs.get_component(entity, PaperSprite)
            
            # e.g., "WALK_DOWN"
            target = f"{state.current_state}_{state.facing}"
            
            # Fallback for LEFT (reuse RIGHT and flip)
            if "LEFT" in state.facing:
                target = target.replace("LEFT", "RIGHT")
                anim.flip_x = True
            else:
                anim.flip_x = False

            # Check if animation exists, if not fallback to IDLE
            if target not in anim.animations:
                target = f"IDLE_{state.facing}".replace("LEFT", "RIGHT")

            # Switch Logic
            if anim.current_anim != target:
                anim.current_anim = target
                anim.frame_index = 0
                anim.frame_timer = 0
        
        # 2. Frame Advancement (For ALL PaperSprites, including Ghosts)
        all_sprites = self.ecs.get_entities_with(PaperSprite)
        for entity in all_sprites:
            anim = self.ecs.get_component(entity, PaperSprite)
            
            frames = anim.animations.get(anim.current_anim)
            if not frames: continue
            
            anim.frame_timer += dt * anim.playback_speed
            if anim.frame_timer >= anim.frame_duration:
                anim.frame_timer = 0
                
                # Logic for Loop Modes
                direction = 1 if anim.playback_speed > 0 else -1
                
                if anim.loop_mode == "PINGPONG":
                    anim.frame_index += (1 * anim._ping_pong_direction)
                    if anim.frame_index >= len(frames):
                        anim.frame_index = len(frames) - 2
                        anim._ping_pong_direction = -1
                    elif anim.frame_index < 0:
                        anim.frame_index = 1
                        anim._ping_pong_direction = 1
                else: # Default LOOP
                    anim.frame_index = (anim.frame_index + 1) % len(frames)

class RenderSystem:
    def __init__(self, ecs, surface):
        self.ecs = ecs
        self.surface = surface
        self.shadow_surf = pygame.Surface((10, 4), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow_surf, COLOR_SHADOW, (0,0,10,4))

    def update(self, camera_offset):
        # Z-Sort: Y position + Z-Index
        renderables = self.ecs.get_entities_with(Transform, PaperSprite)
        renderables.sort(key=lambda e: (
            self.ecs.get_component(e, PaperSprite).z_index,
            self.ecs.get_component(e, Transform).y
        ))

        for entity in renderables:
            trans = self.ecs.get_component(entity, Transform)
            anim = self.ecs.get_component(entity, PaperSprite)
            
            frames = anim.animations.get(anim.current_anim)
            if not frames: continue
            
            # Safety Check
            idx = max(0, min(anim.frame_index, len(frames)-1))
            image = frames[idx].copy()

            # Transformations
            if anim.flip_x:
                image = pygame.transform.flip(image, True, False)
            if anim.rotation != 0:
                image = pygame.transform.rotate(image, anim.rotation)
            if anim.scale != 1.0:
                w = int(image.get_width() * anim.scale)
                h = int(image.get_height() * anim.scale)
                image = pygame.transform.scale(image, (w, h))
            if anim.opacity < 255:
                image.set_alpha(anim.opacity)

            # Draw Shadow
            screen_x = trans.x - camera_offset.x
            screen_y = trans.y - camera_offset.y
            self.surface.blit(self.shadow_surf, (screen_x + 3, screen_y + 12))

            # Draw Sprite
            draw_x = screen_x + anim.offset_y + (trans.width - image.get_width()) // 2
            draw_y = screen_y + anim.offset_y + (trans.height - image.get_height())
            
            self.surface.blit(image, (draw_x, draw_y))

# --- ASSET GENERATOR (Since no .pngs) ---
def generate_anim_frames(color):
    """
    Creates a set of surfaces to mimic a 'bouncing' flipbook.
    Frame 1: Normal
    Frame 2: Squashed (Down)
    Frame 3: Normal
    Frame 4: Stretched (Up)
    """
    base = pygame.Surface((16, 16), pygame.SRCALPHA)
    pygame.draw.rect(base, color, (0, 0, 16, 16), border_radius=3)
    # Add Eyes
    pygame.draw.rect(base, (255,255,255), (3, 4, 4, 4))
    pygame.draw.rect(base, (255,255,255), (9, 4, 4, 4))
    
    # Generate variations
    f1 = base # Normal
    f2 = pygame.transform.scale(base, (18, 14)) # Squash
    f3 = base 
    f4 = pygame.transform.scale(base, (14, 18)) # Stretch
    
    return [f1, f2, f3, f4]

# --- FACTORIES ---

def create_player(ecs, x, y):
    e = ecs.create_entity()
    ecs.add_component(e, Transform(x, y))
    ecs.add_component(e, RigidBody(max_speed=90, friction=12.0))
    ecs.add_component(e, Collider(tag="player"))
    ecs.add_component(e, InputControl())
    ecs.add_component(e, MovementState())
    
    # Generate Assets
    frames = generate_anim_frames(COLOR_PLAYER)
    anims = {
        "IDLE_DOWN": [frames[0]],
        "IDLE_RIGHT": [frames[0]],
        "WALK_DOWN": frames,
        "WALK_UP": frames,     # In real game, use back sprites
        "WALK_RIGHT": frames,
    }
    
    ecs.add_component(e, PaperSprite(animations=anims, loop_mode="LOOP"))
    return e

def create_monster(ecs, x, y):
    e = ecs.create_entity()
    ecs.add_component(e, Transform(x, y))
    ecs.add_component(e, RigidBody(max_speed=40, friction=10.0))
    ecs.add_component(e, Collider(tag="monster"))
    ecs.add_component(e, MovementState())
    
    # AI Logic
    patrol = [(x, y), (x+60, y), (x+60, y+60), (x, y+60)]
    ecs.add_component(e, AIBehavior(state="PATROL", patrol_points=patrol))
    
    frames = generate_anim_frames(COLOR_MONSTER)
    anims = {
        "IDLE_DOWN": [frames[0]],
        "IDLE_RIGHT": [frames[0]],
        "WALK_DOWN": frames,
        "WALK_RIGHT": frames,
    }
    ecs.add_component(e, PaperSprite(animations=anims))
    return e

def create_ghost(ecs, x, y):
    e = ecs.create_entity()
    ecs.add_component(e, Transform(x, y))
    
    # Ghost visual: Just a floaty block
    surf = pygame.Surface((16, 16), pygame.SRCALPHA)
    pygame.draw.circle(surf, COLOR_GHOST, (8, 8), 8)
    # Eyes
    pygame.draw.circle(surf, (0,0,0), (5, 6), 2)
    pygame.draw.circle(surf, (0,0,0), (11, 6), 2)
    
    frames = [surf]
    # To make it float, we change the scale or offset in frames, 
    # but here we'll just let it sit to show transparency
    
    ecs.add_component(e, PaperSprite(
        animations={"default": frames}, 
        loop_mode="PINGPONG",
        opacity=150, # Transparent
        z_index=1 # Draw on top
    ))
    return e

def create_wall(ecs, x, y, w, h):
    e = ecs.create_entity()
    ecs.add_component(e, Transform(x, y, w, h))
    ecs.add_component(e, Collider(tag="wall"))
    
    # Static sprite for wall
    surf = pygame.Surface((w, h))
    surf.fill(COLOR_WALL)
    pygame.draw.rect(surf, (50, 50, 70), (0,0,w,h), 2) # Border
    
    ecs.add_component(e, PaperSprite(
        animations={"default": [surf]},
        current_anim="default"
    ))
    return e

# --- GAME LOOP ---
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.display = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
        pygame.display.set_caption("ECS Flipbook Engine")
        self.clock = pygame.time.Clock()
        self.running = True
        
        self.ecs = ECSManager()
        
        # Init Systems
        self.sys_input = InputSystem(self.ecs)
        self.sys_ai = AISystem(self.ecs)
        self.sys_physics = PhysicsSystem(self.ecs)
        self.sys_anim = AnimationSystem(self.ecs)
        self.sys_render = RenderSystem(self.ecs, self.display)
        
        self.load_level()

    def load_level(self):
        # Walls
        create_wall(self.ecs, 50, 50, 200, 32)
        create_wall(self.ecs, 50, 82, 32, 100)
        
        # Entities
        self.player_id = create_player(self.ecs, 100, 100)
        create_monster(self.ecs, 180, 120)
        create_monster(self.ecs, 80, 200)
        
        # Ghost (Floaty & Transparent)
        create_ghost(self.ecs, 200, 150)

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()

            # Logic
            self.sys_input.update()
            self.sys_ai.update(dt)
            self.sys_physics.update(dt)
            self.sys_anim.update(dt)
            self.ecs.process_destruction()

            # Camera
            p_trans = self.ecs.get_component(self.player_id, Transform)
            cam = pygame.math.Vector2(0,0)
            if p_trans:
                cam.x = p_trans.x - INTERNAL_WIDTH // 2
                cam.y = p_trans.y - INTERNAL_HEIGHT // 2

            # Render
            self.display.fill(COLOR_BG)
            self.sys_render.update(cam)
            
            # Scale
            pygame.transform.scale(self.display, (WINDOW_WIDTH, WINDOW_HEIGHT), self.screen)
            pygame.display.flip()

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    Game().run()
