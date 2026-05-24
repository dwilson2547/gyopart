import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CarPickerV2Component } from './car-picker-v2.component';

describe('CarPickerV2Component', () => {
  let component: CarPickerV2Component;
  let fixture: ComponentFixture<CarPickerV2Component>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ CarPickerV2Component ]
    })
    .compileComponents();

    fixture = TestBed.createComponent(CarPickerV2Component);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
