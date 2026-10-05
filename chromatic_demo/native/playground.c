/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdint.h>
#include <string.h>
#include "playground_assets.h"

/* UI state is deliberately inspectable through the emitted NOI symbols. */
enum { WORLD, MENU, EDITOR, PREVIEW, WAIT, MEANING, REPLY, JOURNAL };
uint8_t phase, ui_id, area, player_x, player_y, npc_id;
uint8_t quest_flags, inventory, draft_length, committed_count, source;
uint8_t cursor, editor_step, editor_group, spelling, outcome_id;
uint8_t draft_revision, context_revision, request_sequence, host_available;
uint8_t reply_page, rejected_responses, gate_open;
uint8_t draft_source;
char draft[97];
char committed_text[97];
volatile uint8_t __at(0xC800) host_mailbox[1024];

static uint8_t previous, pause_phase, heartbeat_value, heartbeat_age,keyboard_page,overflow,hold_frames,no_completion;
static uint16_t wait_frames;
/* Finite design budgets in emulated frames, not measured provider latencies. */
#define WAIT_CLASSIFY 900u
#define WAIT_COMPOSE 2100u
#define WAIT_EXTERNAL 3600u
static uint8_t gesture_length, gesture[4];
static const char *active_reply;
static const char *const modes[9] = {"2 Intent composer", "1 Keyword chips", "3 Initials shorthand", "4 Predictive grid", "5 Grouped alphabet", "6 Custom EdgeWrite", "7 Dasher inspired", "8 Radial groups", "9 Paired host"};
static const char alphabet[] = "abcdefghijklmnopqrstuvwxyz .?'";
static const char keyboard_sets[4][31]={"abcdefghijklmnopqrstuvwxyz .?'","ABCDEFGHIJKLMNOPQRSTUVWXYZ -!,","0123456789-!,:;()/+@#$%*=[]{}\"","\\^`|<>_&.?'0123456789abcdefgh~"};
static const char dasher_order[] = " etaoinshrdlucmfwypvbgkjqxz.?'";
static const char *const common_words[7] = {"ask", "help", "refuse", "route", "name", "trade", "not"};
static const char *const actions[5] = {"DEL", "PREVIEW", "SPELL", "CANCEL", "GET DRAFT"};
static const char *const goals[3] = {"Ask", "Offer", "Refuse"};
static const char *const stances[3] = {"Neutral", "Cautious", "Firm"};
static uint8_t intent_goal,intent_topic;
static uint8_t meaning_pick,reply_is_opening,request_operation;
static const uint8_t rank_order[9]={1,0,2,3,4,5,6,7,8};
static uint8_t branch_start, branch_end;
static uint8_t desired_tiles[360],visible_tiles[360],desired_sprites;
uint8_t font_tiles[95]; /* Loaded font encoding, inspectable for ASCII verification. */

/* Screen builders touch WRAM only. Commit each dirty run to VRAM once, so
 * clearing the desired canvas never erases the visible screen first. */
static void commit_canvas(void) {
    uint8_t row,column,start,length;
    uint16_t offset;
    for(row=0;row<18;row++) {
        column=0;offset=(uint16_t)row*20;
        while(column<20) {
            if(desired_tiles[offset+column]==visible_tiles[offset+column]){column++;continue;}
            start=column;
            while(column<20 && desired_tiles[offset+column]!=visible_tiles[offset+column])column++;
            length=column-start;
            set_bkg_tiles(start,row,length,1,desired_tiles+offset+start);
            memcpy(visible_tiles+offset+start,desired_tiles+offset+start,length);
        }
    }
    if(desired_sprites)SHOW_SPRITES;else HIDE_SPRITES;
}
static void canvas_tiles(uint8_t x,uint8_t y,uint8_t width,uint8_t height,const uint8_t *tiles) {
    uint8_t row,column;
    for(row=0;row<height;row++)for(column=0;column<width;column++)
        desired_tiles[(uint16_t)(y+row)*20+x+column]=tiles[(uint16_t)row*width+column];
}

static void at(uint8_t x, uint8_t y, const char *text) {
    uint8_t c;
    while (*text && x < 20) {c=*text++;desired_tiles[(uint16_t)y*20+x++]=font_tiles[c>=32&&c<=126?c-32:'?'-32];}
}
static void blank(void) {
    desired_sprites=0;
    memset(desired_tiles,font_tiles[0],360);
}
static void number(uint8_t x, uint8_t y, uint8_t value) {
    char text[4];
    text[0]='0'+value/100; text[1]='0'+value/10%10; text[2]='0'+value%10; text[3]=0;
    at(x,y,text);
}
/* Render bounded, word-wrapped text; return the next unread byte offset. */
static uint16_t paragraph(const char *text, uint16_t offset, uint8_t row, uint8_t rows) {
    uint8_t count, cut, i;
    char line[19];
    while (rows-- && text[offset]) {
        while (text[offset]==' ') offset++;
        count=0;
        while (count<18 && text[offset+count]) count++;
        cut=count;
        if (count==18 && text[offset+count] && text[offset+count]!=' ') {
            for (i=count; i>0; i--) if (text[offset+i-1]==' ') { cut=i-1; break; }
            if (!cut) cut=count;
        }
        for (i=0;i<cut;i++) line[i]=text[offset+i];
        line[cut]=0; at(1,row++,line); offset+=cut;
    }
    return offset;
}
static void changed(void) { draft_revision++;draft_source=0;no_completion=0; }
static void append_char(char c) {
    if (draft_length<96) { draft[draft_length++]=c; draft[draft_length]=0; changed();overflow=0; }else overflow=1;
}
static void append_word(const char *text) {
    uint8_t length=strlen(text);
    if (draft_length+length+(draft_length?1:0)>96) {overflow=1;return;}
    if (draft_length && draft[draft_length-1]!=' ') append_char(' ');
    while (*text) append_char(*text++);
}
static void replace_draft(const char *text) {
    if (strlen(text)>96) return;
    strcpy(draft,text); draft_length=strlen(text); changed();
}
static uint8_t npc_near(void) {
    uint8_t i, dx, dy;
    for(i=0;i<NPC_COUNT;i++) if(npc_area[i]==area) {
        dx=player_x>npc_x[i]?player_x-npc_x[i]:npc_x[i]-player_x;
        dy=player_y>npc_y[i]?player_y-npc_y[i]:npc_y[i]-player_y;
        if(dx<=2 && dy<=3) return i;
    }
    return 255;
}
static uint8_t blocked(uint8_t x,uint8_t y) {
    uint8_t i;
    if(x>=20 || y>=14 || area_maps[area][y][x]=='#' || area_maps[area][y][x]=='~') return 1;
    if(area_maps[area][y][x]=='G' && !(quest_flags&128))return 1;
    for(i=0;i<NPC_COUNT;i++) if(npc_area[i]==area && x>=npc_x[i] && x<npc_x[i]+2 && y>=npc_y[i] && y<npc_y[i]+4) return 1;
    if(area==npc_area[0] && x>=npc_x[0]+3 && x<npc_x[0]+5 && y>=npc_y[0] && y<npc_y[0]+4)return 1;
    return 0;
}
static void render_world(void) {
    uint8_t y,i,x,tiles[20];char tile;
    gate_open=quest_flags&128?1:0;
    blank(); at(1,0,area_names[area]); at(1,1,"FICTIONAL TEST WORLD");
    for(y=0;y<14;y++) {for(x=0;x<20;x++){tile=area_maps[area][y][x];tiles[x]=tile=='#'?209:tile==','?210:tile=='~'?211:tile=='G'&&!(quest_flags&128)?212:208;}canvas_tiles(0,y+2,20,1,tiles);}
    for(i=0;i<NPC_COUNT;i++) if(npc_area[i]==area) {canvas_tiles(npc_x[i],npc_y[i]+2,2,4,professor_map);if(i==0)canvas_tiles(npc_x[i]+3,npc_y[i]+2,2,4,rockitten_map);}
    set_sprite_tile(0,0); move_sprite(0,player_x*8+8,(player_y+2)*8+16);desired_sprites=1;
    at(0,16,npc_near()!=255?"A TALK  START MENU":"DPAD WALK START MENU");
    at(0,17,"Quest:"); number(6,17,quest_flags); at(10,17,"Bag:"); number(15,17,inventory);
}
/* Walking changes OAM, not the background map. Refresh only a changed hint. */
static void render_world_movement(uint8_t previous_near) {
    uint8_t near=npc_near()!=255;
    move_sprite(0,player_x*8+8,(player_y+2)*8+16);
    if(near!=previous_near){at(0,16,near?"A TALK  START MENU  ":"DPAD WALK START MENU");commit_canvas();}
}
static uint8_t body_count(void) {
    if(spelling || ui_id==3) return 32;
    if(ui_id==0)return editor_step==1?6:3;
    if(ui_id==2) return 6;
    if(ui_id==1) return 7;
    if(ui_id==4) return editor_step?5:6;
    if(ui_id==5) return 1;
    if(ui_id==6) return branch_end-branch_start<=4?branch_end-branch_start:4;
    if(ui_id==7) return editor_step?(editor_group==3?9:7):4;
    return 1;
}
static uint8_t columns(void) { return spelling||ui_id==3?10:1; }
static const char *prediction(void) {
    uint8_t start=draft_length,i,j;
    while(start && draft[start-1]!=' ')start--;
    for(i=0;i<7;i++) {
        j=0;while(start+j<draft_length && common_words[i][j]==draft[start+j])j++;
        if(j==draft_length-start && common_words[i][j])return common_words[i];
    }
    return "";
}
static uint8_t initials_match(uint8_t choice) {
    const char *text=reply_utterance[npc_id][choice];uint8_t i=0,c,first=1;
    if(!draft_length)return 0;
    while(*text && i<draft_length) {
        c=*text++;
        if(c==' '){first=1;continue;}
        if(first){if(c>='A'&&c<='Z')c+=32;if((uint8_t)draft[i]!=c)return 0;i++;first=0;}
    }
    return i==draft_length;
}
static void render_editor(void) {
    uint8_t i,count=body_count(),start,group_size;
    char item[19];
    blank(); at(1,0,npc_names[npc_id]); at(1,1,modes[ui_id]);
    if(draft_length)paragraph(draft,0,2,3);else paragraph("[empty draft]",0,2,3);
    if(draft_length==96 || overflow) at(1,5,"FULL: DELETE FIRST");
    else { at(1,5,"AUTHORED"); number(15,5,draft_length); }
    if(spelling || ui_id==3) {
        if(no_completion)at(1,6,"No completion");
        for(i=0;i<30;i++) { item[0]=cursor==i?'>':' '; item[1]=keyboard_sets[keyboard_page][i]==' '?'_':keyboard_sets[keyboard_page][i]; item[2]=0; at((i%10)*2,7+i/10,item); }
        at(0,11,cursor==30?">":" "); at(1,11,"Complete:"); at(11,11,prediction());
        at(0,12,cursor==31?">":" ");at(1,12,"PAGE: letters/#/case");
    } else if(ui_id==0) {
        at(1,6,editor_step==0?"GOAL":editor_step==1?"TOPIC":"STANCE");
        for(i=0;i<count;i++) {at(0,7+i,cursor==i?">":" ");at(1,7+i,editor_step==0?goals[i]:editor_step==1?reply_label[npc_id][i]:stances[i]);}
    } else if(ui_id==2) {
        for(i=0;i<6;i++) { at(0,6+i,cursor==i?">":" "); at(1,6+i,initials_match(i)?reply_label[npc_id][i]:"[initials mismatch]"); }
        at(1,12,"SPELL INITIALS FIRST");
    } else if(ui_id==1) {
        for(i=0;i<7;i++) { at(0,6+i,cursor==i?">":" "); at(2,6+i,keyword_chips[npc_id][i]); }
    } else if(ui_id==4) {
        for(i=0;i<count;i++) { at(0,7+i,cursor==i?">":" ");
            if(editor_step) { item[0]=alphabet[editor_group*5+i]; item[1]=0; }
            else {for(start=0;start<5;start++)item[start]=alphabet[i*5+start];item[5]=0;}
            at(2,7+i,item);
        }
        at(1,12,editor_step?"A LETTER B GROUPS":"A GROUP THEN LETTER");
    } else if(ui_id==5) {
        for(i=0;i<30;i++) {
            uint8_t n=i<4?1:i<20?2:3,v=i<4?i:i<20?i-4:i-20,k;
            for(k=n;k>0;k--) {item[k-1]="URDL"[v%4];v/=4;}
            item[n]='=';item[n+1]=alphabet[i]==' '?'_':alphabet[i];item[n+2]=0;
            at((i%3)*6,6+i/3,item);
        }
        at(1,16,"TRACE:");for(i=0;i<gesture_length;i++){item[0]="URDL"[gesture[i]];item[1]=0;at(8+i*2,16,item);}
    } else if(ui_id==6) {
        group_size=(branch_end-branch_start+3)/4;
        for(i=0;i<count;i++) { at(0,7+i,cursor==i?">":" "); start=branch_start+i*group_size;
            if(start>=branch_end) { at(2,7+i,"[empty]"); continue; }
            memcpy(item,dasher_order+start,branch_end-start<group_size?branch_end-start:group_size);
            item[branch_end-start<group_size?branch_end-start:group_size]=0; at(2,7+i,item);
        }
        at(1,12,"A ZOOM B REVERSE");
    } else if(ui_id==7) {
        if(!editor_step) { at(1,7,"      UP: A-G"); at(1,9,"LEFT V-?  RIGHT H-N"); at(1,11,"      DOWN: O-U"); }
        else for(i=0;i<count;i++) { item[0]=cursor==i?'>':' '; item[1]=alphabet[editor_group*7+i]; item[2]=0; at(1+(i%4)*4,7+i/4,item); }
        at(1,12,"A SELECT B PETALS");
    } else {
        at(0,7,cursor==0?">":" "); at(1,7,"RECEIVE HOST TEXT");
        at(1,9,host_available?"PYBOY HOST CONNECTED":"HOST UNAVAILABLE");
        at(1,10,"USB: NO LIVE BRIDGE"); at(1,12,"SPELL WORKS OFFLINE");
    }
    if(ui_id!=5 || spelling || cursor>=count)for(i=0;i<5;i++) { at((i%2)*10,14+i/2,cursor==count+i?">":" "); at((i%2)*10+1,14+i/2,actions[i]); }
    at(0,17,ui_id==5&&!spelling&&cursor<count?"A LETTER B ACTIONS":"A CHOOSE START MENU");
}
static void compose_screen(void) {
    uint8_t i,start;
    uint16_t offset,next;
    if(phase==WORLD) { render_world(); return; }
    if(phase==EDITOR) { render_editor(); return; }
    blank();
    if(phase==MENU) {
        at(1,0,"CONVERSATION LAB"); at(1,1,"RANK: DESIGN JUDGMENT");
        start=cursor<7?0:cursor-6;
        if(start>5)start=5;
        for(i=0;i<7 && start+i<12;i++) {
            at(0,3+i,cursor==start+i?">":" ");
            if(start+i<9) at(1,3+i,modes[rank_order[start+i]]);
            else at(1,3+i,start+i==9?"Journal / inventory":start+i==10?"Reset test world":"Return");
        }
        at(1,13,"A CHOOSE B RESUME"); at(1,15,"Unsent draft kept"); at(1,17,"START ALSO RESUMES");
    } else if(phase==PREVIEW) {
        at(1,0,"EXACT OUTGOING TEXT"); paragraph(draft,0,2,6);
        at(1,8,draft_source==2?"HOST GENERATED DRAFT":draft_source==3?"PAIRED PLAYER TEXT":"PLAYER/AUTHORED TEXT");
        at(1,10,"A DOES NOT AUTOSEND");
        at(0,13,cursor==0?">":" "); at(2,13,"SEND THIS TEXT");
        at(0,14,cursor==1?">":" "); at(2,14,"EDIT");
        at(0,15,cursor==2?">":" "); at(2,15,"CANCEL");
    } else if(phase==WAIT) {
        at(1,0,"HOST REQUEST"); at(1,3,"Waiting for PyBoy"); at(1,5,"B cancels safely"); at(1,8,"Timeout keeps draft");
    } else if(phase==MEANING) {
        at(1,0,"CONFIRM THE MEANING"); at(1,1,source==0?"AUTHORED RULES":source==1?"HOST LOCAL MODEL":"HOST REMOTE MODEL");
        if(meaning_pick) {for(i=0;i<6;i++){at(0,4+i,cursor==i?">":" ");at(1,4+i,reply_label[npc_id][i]);}at(1,14,"A PICK THEN CONFIRM");return;}
        paragraph(committed_text,0,3,5);
        at(1,9,outcome_id<6?reply_label[npc_id][outcome_id]:"No known intent");
        at(0,12,cursor==0?">":" "); at(2,12,"YES, THAT MEANING");
        at(0,13,cursor==1?">":" "); at(2,13,"CHOOSE MEANING");
        at(0,14,cursor==2?">":" "); at(2,14,"EDIT TEXT");
        at(1,17,"No reward yet");
    } else if(phase==REPLY) {
        at(1,0,npc_names[npc_id]); at(1,1,source==0?"AUTHORED TEST REPLY":"HOST / AUTHORED REPLY");
        offset=0; for(i=0;i<reply_page;i++) offset=paragraph(active_reply,offset,3,9);
        /* Clear page rows after seeking, because seeking rendered earlier pages. */
        for(i=3;i<12;i++) at(0,i,"                    ");
        next=paragraph(active_reply,offset,3,9);
        at(1,14,active_reply[next]?"A NEXT PAGE":"A CONTINUE"); at(1,16,"B BACK TO WORLD");
    } else {
        at(1,0,"JOURNAL / INVENTORY"); at(1,2,"AUTHORED TEST STATE"); at(1,4,"Quest flags:"); number(14,4,quest_flags);
        at(1,6,"Item bits:"); number(14,6,inventory);
        at(1,8,"Flags unlock routes"); at(1,10,"Items guard trades"); at(1,12,"A / B RETURN");
        at(1,8,inventory&1?"Aid kit: yes":"Aid kit: spent");at(1,9,inventory&2?"Crystal: yes":"Crystal: traded");at(1,10,inventory&4?"Permit: yes":"Permit: needed");at(1,11,inventory&8?"Supply pack: yes":"Supply pack: needed");
    }
}
static void render(void){compose_screen();commit_canvas();}
static void start_request(uint8_t operation) {
    uint8_t i;
    request_sequence++;
    request_operation=operation;
    host_mailbox[6]=operation; host_mailbox[7]=request_sequence;
    host_mailbox[8]=context_revision; host_mailbox[9]=draft_revision;
    host_mailbox[10]=npc_id; host_mailbox[11]=ui_id;
    host_mailbox[12]=operation==3?0:draft_length;
    for(i=0;i<host_mailbox[12];i++) host_mailbox[24+i]=draft[i];
    host_mailbox[5]=1; wait_frames=0; phase=WAIT;
}
static uint8_t contains_keyword(const char *text,const char *keys) {
    char key[25]; uint8_t len=0,i,j;
    while(1) {
        if(*keys=='|' || !*keys) {
            key[len]=0;
            if(len)for(i=0;text[i];i++){j=0;while(j<len && text[i+j]==key[j])j++;if(j==len)return 1;}
            len=0;
            if(!*keys)break;
        } else if(len<24) key[len++]=*keys;
        keys++;
    }
    return 0;
}
static void classify_authored(void) {
    char lower[97]; uint8_t i,c;
    for(i=0;i<draft_length;i++) { c=committed_text[i]; lower[i]=(c>='A' && c<='Z')?c+32:c; }
    lower[draft_length]=0; outcome_id=255;
    for(i=0;i<6;i++) if(!strcmp(committed_text,reply_utterance[npc_id][i]) || contains_keyword(lower,reply_keywords[npc_id][i])) { outcome_id=i; break; }
    source=0; phase=MEANING; cursor=0;meaning_pick=0;
}
static void commit_send(void) {
    if(!draft_length)return;
    strcpy(committed_text,draft); committed_count++;
    if(host_available) start_request(1); else classify_authored();
}
static void begin_editor(void) {
    phase=EDITOR; cursor=0; editor_step=0; spelling=0; gesture_length=0; branch_start=0; branch_end=30;
}
static void apply_meaning(void) {
    uint8_t needs,forbids,accepted=0;
    if(npc_near()!=npc_id){active_reply="Come back beside me before we make that agreement.";}
    else if(outcome_id>=6) {
        active_reply="I do not know what you mean. Try a different message or choose a meaning yourself.";
    } else {
        needs=reply_requires_flags[npc_id][outcome_id]; forbids=reply_forbids_flags[npc_id][outcome_id];
        if((quest_flags & needs)!=needs || (quest_flags & forbids) || (inventory & reply_requires_items[npc_id][outcome_id]) != reply_requires_items[npc_id][outcome_id]) active_reply="That choice needs a different quest state. Visit the other expedition members first. Your words were kept.";
        else { quest_flags|=reply_set_flags[npc_id][outcome_id]; inventory&=~reply_spend_item[npc_id][outcome_id]; inventory|=reply_give_item[npc_id][outcome_id]; context_revision++; active_reply=reply_text[npc_id][outcome_id];accepted=1; }
    }
    phase=REPLY; reply_page=0; cursor=0;reply_is_opening=0;
    if(accepted){draft_length=0;draft[0]=0;changed();}
}
static void editor_input(uint8_t pressed) {
    uint8_t count=body_count(),col=columns(),i,size,value;
    if(ui_id==5 && !spelling && cursor<count) {
        if(pressed & (J_UP|J_RIGHT|J_DOWN|J_LEFT)) {
            value=pressed&J_UP?0:pressed&J_RIGHT?1:pressed&J_DOWN?2:3;
            if(gesture_length<3)gesture[gesture_length++]=value;
        }
        if(pressed & J_A) {
            value=0; for(i=0;i<gesture_length;i++)value=value*4+gesture[i];
            if(gesture_length==1)append_char(alphabet[value]);
            else if(gesture_length==2)append_char(alphabet[4+value]);
            else if(gesture_length==3 && value<10)append_char(alphabet[20+value]);
            gesture_length=0;
        }
        if(pressed & J_B) { if(gesture_length)gesture_length--; else cursor=count; }
        return;
    }
    if(ui_id==7 && !spelling && !editor_step && cursor<count) {
        if(pressed&J_UP)editor_group=0;
        if(pressed&J_RIGHT)editor_group=1;
        if(pressed&J_DOWN)editor_group=2;
        if(pressed&J_LEFT)editor_group=3;
        if(pressed&J_A) { editor_step=1; cursor=0; }
        if(pressed&J_B)cursor=count;
        return;
    }
    if(pressed&J_B) {
        if(spelling) { spelling=0; cursor=0; }
        else if(editor_step) { editor_step=0; cursor=0; }
        else if(ui_id==6 && (branch_start || branch_end<30)) { branch_start=0; branch_end=30; cursor=0; }
        else { phase=WORLD; }
        return;
    }
    if(pressed&J_DOWN)cursor=(cursor+col<count+5)?cursor+col:count;
    if(pressed&J_UP)cursor=cursor>=col?cursor-col:count+4;
    if(pressed&J_RIGHT)cursor=cursor+1<count+5?cursor+1:0;
    if(pressed&J_LEFT)cursor=cursor?cursor-1:count+4;
    if(!(pressed&J_A))return;
    if(cursor>=count) {
        switch(cursor-count) {
            case 0: if(draft_length) { draft[--draft_length]=0;changed();overflow=0; } break;
            case 1: if(draft_length) { phase=PREVIEW;cursor=0; } break;
            case 2: spelling=1;cursor=0; break;
            case 3: phase=WORLD;break;
            case 4: if(draft_length){if(host_available)start_request(2);else {phase=PREVIEW;cursor=0;}}break;
        }
    } else if(spelling || ui_id==3) {
        if(cursor<30)append_char(keyboard_sets[keyboard_page][cursor]);
        else if(cursor==31)keyboard_page=(keyboard_page+1)%4;
        else { const char *word=prediction();uint8_t prefix_length,word_length;i=draft_length;while(i&&draft[i-1]!=' ')i--;prefix_length=draft_length-i;word_length=strlen(word);if(!word_length || prefix_length>=word_length){no_completion=1;}else {word+=prefix_length;while(*word)append_char(*word++);} }
    } else if(ui_id==0) {
        if(editor_step==0){intent_goal=cursor;editor_step=1;cursor=0;}
        else if(editor_step==1){intent_topic=cursor;editor_step=2;cursor=0;}
        else {i=cursor;draft_length=0;draft[0]=0;append_word(intent_goal==0?"Can we discuss this:":intent_goal==1?"I offer help with:":"I do not agree with:");append_word(reply_label[npc_id][intent_topic]);append_char(intent_goal==0?'?':'.');if(i==1)append_word("I want a cautious plan.");else if(i==2)append_word("This matters to me.");editor_step=0;cursor=0;}
    } else if(ui_id==2) {if(initials_match(cursor))replace_draft(reply_utterance[npc_id][cursor]);}
    else if(ui_id==1)append_word(keyword_chips[npc_id][cursor]);
    else if(ui_id==4) {
        if(editor_step) { append_char(alphabet[editor_group*5+cursor]); editor_step=0;cursor=0; }
        else { editor_group=cursor;editor_step=1;cursor=0; }
    } else if(ui_id==6) {
        size=(branch_end-branch_start+3)/4;
        i=branch_start+cursor*size;
        if(i>=branch_end)return;
        if(size==1) { append_char(dasher_order[i]);branch_start=0;branch_end=30;cursor=0; }
        else { branch_end=i+size<branch_end?i+size:branch_end;branch_start=i;cursor=0; }
    } else if(ui_id==7) { append_char(alphabet[editor_group*7+cursor]);editor_step=0;cursor=0; }
    else if(ui_id==8 && host_available)start_request(3);
}
static void reset_world(void) {
    area=initial_state[0];player_x=initial_state[1];player_y=initial_state[2];npc_id=0;quest_flags=initial_state[3];inventory=initial_state[4];draft_length=0;draft[0]=0;committed_count=0;source=0;context_revision++;draft_revision++;phase=WORLD;ui_id=1;
}
static void poll_host(void) {
    uint8_t i,status;
    if(host_mailbox[16]!=heartbeat_value) { heartbeat_value=host_mailbox[16];heartbeat_age=0;host_available=1; }
    else if(++heartbeat_age==240) { host_available=0;heartbeat_age=239; }
    if(phase!=WAIT)return;
    status=host_mailbox[5];
    if(status==3 || status==4) {
        if(host_mailbox[7]!=request_sequence || host_mailbox[8]!=context_revision || host_mailbox[9]!=draft_revision || host_mailbox[10]!=npc_id || host_mailbox[6]!=request_operation) { rejected_responses++;host_mailbox[5]=0;begin_editor();return; }
        if(status==4) { host_mailbox[5]=0; if(host_mailbox[6]!=1)begin_editor();else classify_authored();return; }
        if(host_mailbox[6]==3 || host_mailbox[6]==2) {
            if(host_mailbox[13]>96) { rejected_responses++;begin_editor(); }
            else { for(i=0;i<host_mailbox[13];i++)if(host_mailbox[128+i]<32||host_mailbox[128+i]>126)break;
                if(i!=host_mailbox[13]) { rejected_responses++;begin_editor(); }
                else { for(i=0;i<host_mailbox[13];i++)draft[i]=host_mailbox[128+i];draft_length=i;draft[i]=0;changed();draft_source=host_mailbox[6]==3?3:host_mailbox[15];phase=PREVIEW;cursor=0; }
            }
        } else { outcome_id=host_mailbox[14]<6?host_mailbox[14]:255;source=host_mailbox[15]<=2?host_mailbox[15]:0;phase=MEANING;cursor=0;meaning_pick=0; }
        host_mailbox[5]=0;
    } else if(!host_available || ++wait_frames>(request_operation==1?WAIT_CLASSIFY:request_operation==2?WAIT_COMPOSE:WAIT_EXTERNAL)) { host_mailbox[5]=5;if(request_operation!=1)begin_editor();else classify_authored(); }
}
void main(void) {
    uint8_t keys,pressed,x,y,near,i,old_phase,old_area,old_quest,old_inventory,old_near;
    uint16_t offset;
    const palette_color_t palette[]={RGB(31,31,28),RGB(23,25,20),RGB(10,14,12),RGB(1,4,5)};
    DISPLAY_OFF;font_init();font_load(font_ibm);set_bkg_data(192,16,art_tiles);set_bkg_data(208,5,terrain_tiles);set_sprite_data(0,1,player_tiles);
    /* Learn the loaded font's real tile encoding through GBDK while LCD is off.
     * This keeps printable ASCII and font ownership independent of our renderer. */
    for(i=0;i<95;i++){gotoxy(0,0);setchar(i+32);font_tiles[i]=get_bkg_tile_xy(0,0);}
    memset(visible_tiles,255,360);
    BGP_REG=0xe4;OBP0_REG=0xe4;if(_cpu==CGB_TYPE) { set_bkg_palette(0,1,palette);set_sprite_palette(0,1,palette); }
    for(offset=0;offset<1024;offset++)host_mailbox[offset]=0;
    host_mailbox[0]='T';host_mailbox[1]='X';host_mailbox[2]='M';host_mailbox[3]='B';host_mailbox[4]=1;heartbeat_age=239;
    reset_world();render();SHOW_BKG;DISPLAY_ON;
    while(1) {
        wait_vbl_done();keys=joypad();pressed=keys&~previous;previous=keys;old_phase=phase;
        old_area=area;old_quest=quest_flags;old_inventory=inventory;old_near=npc_near()!=255;poll_host();
        if(phase==WORLD && keys&(J_UP|J_DOWN|J_LEFT|J_RIGHT)){if(pressed&(J_UP|J_DOWN|J_LEFT|J_RIGHT))hold_frames=0;else if(++hold_frames>=10){pressed|=keys&(J_UP|J_DOWN|J_LEFT|J_RIGHT);hold_frames=5;}}else hold_frames=0;
        if(!pressed) { if(old_phase!=phase)render();continue; }
        if(pressed&J_START) {
            if(phase==MENU)phase=pause_phase;
            else if(phase!=WAIT) { pause_phase=phase;phase=MENU;for(i=0;i<9;i++)if(rank_order[i]==ui_id)cursor=i; }
        } else if(phase==WORLD) {
            x=player_x;y=player_y;
            if(pressed&J_LEFT && x)x--;if(pressed&J_RIGHT)x++;if(pressed&J_UP && y)y--;if(pressed&J_DOWN)y++;
            if(!blocked(x,y)) {player_x=x;player_y=y;}
            for(i=0;i<EXIT_COUNT;i++)if(area==exits[i][0] && player_x==exits[i][1] && player_y==exits[i][2] && (quest_flags&exits[i][6])==exits[i][6]) {area=exits[i][3];player_x=exits[i][4];player_y=exits[i][5];context_revision++;break;}
            if(pressed&J_A) {near=npc_near();if(near!=255) { if(npc_id!=near){npc_id=near;draft_length=0;draft[0]=0;changed();}active_reply=openings[npc_id];reply_page=0;reply_is_opening=1;source=0;phase=REPLY;} }
        } else if(phase==MENU) {
            if(pressed&J_DOWN)cursor=(cursor+1)%12;if(pressed&J_UP)cursor=cursor?cursor-1:11;
            if(pressed&J_B)phase=pause_phase;
            if(pressed&J_A) { if(cursor<9) {ui_id=rank_order[cursor];if(pause_phase==WORLD)phase=WORLD;else begin_editor();}else if(cursor==9)phase=JOURNAL;else if(cursor==10)reset_world();else phase=pause_phase; }
        } else if(phase==EDITOR)editor_input(pressed);
        else if(phase==PREVIEW) {
            if(pressed&J_DOWN)cursor=(cursor+1)%3;if(pressed&J_UP)cursor=cursor?cursor-1:2;
            if(pressed&J_B)begin_editor();
            if(pressed&J_A) {if(!cursor)commit_send();else if(cursor==1)begin_editor();else phase=WORLD;}
        } else if(phase==WAIT) {if(pressed&J_B){host_mailbox[5]=5;begin_editor();}}
        else if(phase==MEANING) {
            if(pressed&J_DOWN)cursor=(cursor+1)%(meaning_pick?6:3);if(pressed&J_UP)cursor=cursor?cursor-1:(meaning_pick?5:2);
            if(pressed&J_B)begin_editor();
            if(pressed&J_A) {if(meaning_pick){outcome_id=cursor;meaning_pick=0;cursor=0;source=0;}else if(!cursor)apply_meaning();else if(cursor==1){source=0;meaning_pick=1;cursor=0;}else begin_editor();}
        } else if(phase==REPLY) {
            if(pressed&J_B)phase=WORLD;
            if(pressed&J_A) {offset=0;for(x=0;x<=reply_page;x++)offset=paragraph(active_reply,offset,3,9);if(active_reply[offset])reply_page++;else if(reply_is_opening)begin_editor();else phase=WORLD;}
        } else if(phase==JOURNAL && pressed&(J_A|J_B))phase=MENU;
        if(old_phase==WORLD && phase==WORLD && old_area==area && old_quest==quest_flags && old_inventory==inventory)render_world_movement(old_near);
        else render();
    }
}
