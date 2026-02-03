import pygame
import sys
import random

WINDOW_WIDTH = 640
WINDOW_HEIGHT = 480

INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 240

FPS = 60

COLOR_BG = (15, 15, 20)      # Dark Void
COLOR_WALL = (85, 98, 112)   # Slate Blue
COLOR_PLAYER = (255, 107, 107) # Salmon Red
COLOR_ATTACK = (255, 255, 255) # Pure White Slash
COLOR_ENEMY = (78, 205, 196)   # Teal
COLOR_DEBUG_HITBOX = (255, 255, 0)

BTN_A = 0 
BTN_B = 1 
BTN_X = 2 
BTN_Y = 3
AXIS_DEADZONE = 0.2

class InputManager:
    """
    Decouples hardware (Keyboard/Gamepad) from Game Logic.
    """
    def __init__(self):
        self.joysticks = {}
        self._init_controllers()

    def _init_controllers(self):
        for i in range(pygame.joystick.get_count()):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            self.joysticks[joy.get_instance_id()] = joy

    def handle_hotplug(self, event):
        if event.type == pygame.JOYDEVICEADDED:
            joy = pygame.joystick.Joystick(event.device_index)
            self.joysticks[joy.get_instance_id()] = joy
        elif event.type == pygame.JOYDEVICEREMOVED:
            if event.instance_id in self.joysticks:
                del self.joysticks[event.instance_id]

    def get_movement_vector(self):
        move = pygame.math.Vector2(0, 0)
        
        # Keyboard
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]: move.x = -1
        if keys[pygame.K_RIGHT]: move.x = 1
        if keys[pygame.K_UP]: move.y = -1
        if keys[pygame.K_DOWN]: move.y = 1

        # Controller (Overrides keyboard if active)
        if self.joysticks:
            joy = list(self.joysticks.values())[0]
            if abs(joy.get_axis(0)) > AXIS_DEADZONE: move.x = joy.get_axis(0)
            if abs(joy.get_axis(1)) > AXIS_DEADZONE: move.y = joy.get_axis(1)

        if move.length() > 0:
            move = move.normalize()
        return move

    def is_attack_pressed(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_z] or keys[pygame.K_SPACE]: return True
        
        if self.joysticks:
            joy = list(self.joysticks.values())[0]
            if joy.get_button(BTN_X) or joy.get_button(BTN_A): return True
        return False

# --- TIER III: GAMEPLAY & PHYSICS ---
class Entity(pygame.sprite.Sprite):
    def __init__(self, x, y, w, h, color):
        super().__init__()
        self.image = pygame.Surface((w, h))
        self.image.fill(color)
        self.rect = self.image.get_rect(topleft=(x, y))
        self.position = pygame.math.Vector2(x, y)

class Player(Entity):
    def __init__(self, x, y):
        # 16x16 is standard for 320x240 res
        super().__init__(x, y, 16, 16, COLOR_PLAYER)
        self.speed = 80 # Slower speed for smaller resolution
        self.facing_dir = pygame.math.Vector2(0, 1)
        self.state = "IDLE"
        self.attack_timer = 0
        self.attack_rect = None

    def update(self, dt, input_mgr, walls, enemies):
        if self.state == "ATTACK":
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.state = "IDLE"
                self.attack_rect = None
            return 

        move = input_mgr.get_movement_vector()
        
        if input_mgr.is_attack_pressed():
            self.start_attack()
        elif move.length() > 0:
            self.state = "WALK"
            self.facing_dir = move.copy()
            self.move_and_slide(move, dt, walls)
        else:
            self.state = "IDLE"

    def start_attack(self):
        self.state = "ATTACK"
        self.attack_timer = 0.25 # Fast swing
        
        offset = self.facing_dir * 12
        self.attack_rect = pygame.Rect(0, 0, 20, 20)
        self.attack_rect.center = (self.rect.centerx + offset.x, self.rect.centery + offset.y)

    def move_and_slide(self, velocity, dt, walls):
        # Independent Axis Movement for sliding
        self.position.x += velocity.x * self.speed * dt
        self.rect.x = round(self.position.x)
        if pygame.sprite.spritecollide(self, walls, False):
            if velocity.x > 0: self.rect.right = pygame.sprite.spritecollide(self, walls, False)[0].rect.left
            if velocity.x < 0: self.rect.left = pygame.sprite.spritecollide(self, walls, False)[0].rect.right
            self.position.x = self.rect.x

        self.position.y += velocity.y * self.speed * dt
        self.rect.y = round(self.position.y)
        if pygame.sprite.spritecollide(self, walls, False):
            if velocity.y > 0: self.rect.bottom = pygame.sprite.spritecollide(self, walls, False)[0].rect.top
            if velocity.y < 0: self.rect.top = pygame.sprite.spritecollide(self, walls, False)[0].rect.bottom
            self.position.y = self.rect.y

    def draw(self, surface, cam_offset):
        pos = (self.rect.x - cam_offset.x, self.rect.y - cam_offset.y)
        surface.blit(self.image, pos)
        
        # Debug Attack Box
        if self.state == "ATTACK" and self.attack_rect:
            dbg_pos = (self.attack_rect.x - cam_offset.x, self.attack_rect.y - cam_offset.y)
            pygame.draw.rect(surface, COLOR_ATTACK, (*dbg_pos, self.attack_rect.w, self.attack_rect.h))

class Camera:
    def __init__(self):
        self.offset = pygame.math.Vector2(0, 0)
    
    def update(self, target):
        # Keep player centered in the small internal resolution
        self.offset.x = target.rect.centerx - INTERNAL_WIDTH // 2
        self.offset.y = target.rect.centery - INTERNAL_HEIGHT // 2

# --- ENGINE ---
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        
        self.display_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
        
        pygame.display.set_caption("Tiny ARPG")
        self.clock = pygame.time.Clock()
        self.running = True
        
        self.input_mgr = InputManager()
        self.camera = Camera()
        
        # Groups
        self.all_sprites = pygame.sprite.Group()
        self.walls = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()
        
        self.init_level()

    def init_level(self):
        self.player = Player(100, 80)
        self.all_sprites.add(self.player)

        for _ in range(15):
            x = random.randint(0, 500)
            y = random.randint(0, 400)
            wall = Entity(x, y, 32, 32, COLOR_WALL)
            self.walls.add(wall)
            self.all_sprites.add(wall)

        # Create a dummy enemy
        enemy = Entity(150, 150, 16, 16, COLOR_ENEMY)
        self.enemies.add(enemy)
        self.all_sprites.add(enemy)

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

            # Input
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                # Toggle Fullscreen with F11
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                self.input_mgr.handle_hotplug(event)

            # Update
            self.player.update(dt, self.input_mgr, self.walls, self.enemies)
            self.camera.update(self.player)
            
            # Simple Hitbox Logic
            if self.player.state == "ATTACK" and self.player.attack_rect:
                hits = [e for e in self.enemies if self.player.attack_rect.colliderect(e.rect)]
                for e in hits:
                    e.kill()
                    print("Enemy Slain!")

            # Draw (Render to low-res surface first)
            self.display_surface.fill(COLOR_BG)
            
            for sprite in self.all_sprites:
                offset_pos = (sprite.rect.x - self.camera.offset.x, 
                              sprite.rect.y - self.camera.offset.y)
                self.display_surface.blit(sprite.image, offset_pos)
            
            self.player.draw(self.display_surface, self.camera.offset)

            # Scale up to window size
            pygame.transform.scale(self.display_surface, (self.screen.get_width(), self.screen.get_height()), self.screen)
            
            pygame.display.flip()

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    Game().run()

